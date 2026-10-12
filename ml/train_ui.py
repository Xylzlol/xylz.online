"""Fine-tune UNISAL (pretrained, Apache-2.0) on UEyes 3-second heatmaps (CC BY 4.0) for UI saliency.

Built for wall-clock time without giving up quality:
- every image, heatmap and fixation map is decoded once (threads) and kept on the GPU as uint8
- bf16 autocast, channels_last, cudnn.benchmark; no DataLoader
- loss and early stopping follow UNISAL: KLD - 0.1 NSS - 0.1 CC, best checkpoint by validation loss
- the pretrained model is scored on the same held-out split first, so the gain is measured, not assumed
"""
import csv, json, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

ROOT = Path(__file__).parent
# load the model package without its training-time __init__ (tensorboardX, cv2 ...)
import types  # noqa: E402
_pkg = types.ModuleType("unisal")
_pkg.__path__ = [str(ROOT / "unisal" / "unisal")]
sys.modules["unisal"] = _pkg
from unisal.model import UNISAL  # noqa: E402
from unisal import utils as U  # noqa: E402

DATA = ROOT / "data" / "UEyes_dataset"
H, W = 288, 448
dev = torch.device("cuda")
torch.backends.cudnn.benchmark = True
torch.manual_seed(0)
np.random.seed(0)


def split():
    rows = list(csv.DictReader(open(DATA / "image_types.csv", encoding="utf-8-sig"), delimiter=";"))
    keys = {k.lower(): k for k in rows[0]}
    def col(r, *names):
        for n in names:
            for k in keys:
                if n in k:
                    return r[keys[k]].strip()
        return ""
    out = []
    for r in rows:
        name = col(r, "image", "name", "file")
        cat = col(r, "type", "category").lower()
        part = col(r, "train", "split", "set").lower()
        out.append((name, cat, part))
    return out


def load(name):
    stem = Path(name).stem
    img = next((p for p in (DATA / "images").glob(stem + ".*")), None)
    hm = next((p for p in (DATA / "saliency_maps" / "heatmaps_3s").glob(stem + ".*")), None)
    fx = next((p for p in (DATA / "saliency_maps" / "fixmaps_3s").glob(stem + ".*")), None)
    if not (img and hm and fx):
        return None
    im = Image.open(img).convert("RGB")
    ar = im.width / im.height
    im = np.asarray(im.resize((W, H), Image.BICUBIC), dtype=np.uint8)
    sal = np.asarray(Image.open(hm).convert("L").resize((W, H), Image.BILINEAR), dtype=np.uint8)
    fix = Image.open(fx).convert("L")
    # fixation points survive downscaling as a max-pool of the binary map
    fx_t = torch.from_numpy(np.asarray(fix, dtype=np.uint8) > 0).float()[None, None]
    fx_t = F.adaptive_max_pool2d(fx_t, (H, W))[0, 0].to(torch.uint8).numpy()
    return im, sal, fx_t, ar


def main():
    t0 = time.time()
    rows = split()
    cats = sorted({c for _, c, _ in rows})
    print("categories:", cats, "| split values:", sorted({p for *_, p in rows}))
    keep = [r for r in rows if ("web" in r[1] or "desktop" in r[1])]
    with ThreadPoolExecutor(16) as ex:
        loaded = list(ex.map(lambda r: (r, load(r[0])), keep))
    loaded = [(r, d) for r, d in loaded if d is not None]
    is_test = lambda r: "test" in r[2]
    pool = [(r, d) for r, d in loaded if not is_test(r)]
    rng = np.random.RandomState(0)
    order = rng.permutation(len(pool))
    nval = len(pool) // 10
    va = [pool[i] for i in order[:nval]]  # early stopping only
    tr = [pool[i] for i in order[nval:]]
    te = [(r, d) for r, d in loaded if is_test(r)]  # official test split, scored once at the end
    tw = [(r, d) for r, d in te if "web" in r[1]]
    print(f"train {len(tr)}  val {len(va)}  test {len(te)} (web {len(tw)})  loaded in {time.time() - t0:.1f}s")

    def to_gpu(items):
        X = torch.from_numpy(np.stack([d[0] for _, d in items])).permute(0, 3, 1, 2).contiguous().to(dev)
        S = torch.from_numpy(np.stack([d[1] for _, d in items]))[:, None].to(dev)
        Fx = torch.from_numpy(np.stack([d[2] for _, d in items]))[:, None].to(dev)
        return X, S, Fx
    Xtr, Str, Ftr = to_gpu(tr)
    Xva, Sva, Fva = to_gpu(va)
    Xte, Ste, Fte = to_gpu(te)
    Xtw, Stw, Ftw = to_gpu(tw)
    mean = torch.tensor([0.485, 0.456, 0.406], device=dev).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device=dev).view(1, 3, 1, 1)
    norm = lambda x: ((x.float() / 255 - mean) / std).contiguous(memory_format=torch.channels_last)

    cfg = json.load(open(ROOT / "unisal/training_runs/pretrained_unisal/UNISAL.json"))
    cfg["cnn_cfg"]["pretrained"] = False
    cfg.pop("verbose", None)
    model = UNISAL(**cfg).to(dev).to(memory_format=torch.channels_last)
    model.load_state_dict(torch.load(ROOT / "unisal/training_runs/pretrained_unisal/weights_best.pth", map_location=dev))

    def predict(x):
        return model(x[:, None], source="SALICON", static=True)[:, 0]  # log-probabilities [B,1,H,W]

    def losses(logp, sal, fix):
        sal = sal.float()
        sal = sal / sal.flatten(1).sum(1).clamp_min(1e-8).view(-1, 1, 1, 1)
        kld = U.kld_loss(logp[:, None], sal[:, None])
        nss = U.nss(logp[:, None].exp(), fix[:, None].bool())
        cc = U.corr_coeff(logp[:, None].exp(), sal[:, None])
        return kld.mean(), nss.mean(), cc.mean()

    @torch.no_grad()
    def evaluate(X, S_, F_):
        model.eval()
        k = n = c = 0.0
        for i in range(0, len(X), 32):
            with torch.autocast("cuda", dtype=torch.bfloat16):
                lp = predict(norm(X[i:i + 32]))
            a, b, d = losses(lp.float(), S_[i:i + 32], F_[i:i + 32])
            m = len(X[i:i + 32])
            k += a.item() * m; n += b.item() * m; c += d.item() * m
        N = len(X)
        return {"kld": k / N, "nss": n / N, "cc": c / N}

    base = {"test": evaluate(Xte, Ste, Fte), "test_web": evaluate(Xtw, Stw, Ftw), "val": evaluate(Xva, Sva, Fva)}
    print("pretrained  ", {s: {k: round(v, 4) for k, v in m.items()} for s, m in base.items()})

    opt = torch.optim.AdamW([
        {"params": model.cnn.parameters(), "lr": 4e-5},
        {"params": [p for n, p in model.named_parameters() if not n.startswith("cnn.")], "lr": 4e-4},
    ], weight_decay=1e-4)
    EPOCHS, B = 30, 24
    steps = EPOCHS * ((len(Xtr) + B - 1) // B)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[4e-5, 4e-4], total_steps=steps, pct_start=0.1)
    best, best_ep, patience = None, -1, 6
    for ep in range(EPOCHS):
        model.train()
        perm = torch.randperm(len(Xtr), device=dev)
        for i in range(0, len(perm), B):
            idx = perm[i:i + B]
            x = Xtr[idx]
            # light, layout-preserving augmentation: brightness/contrast jitter only (no flips:
            # UI attention has a left/top bias that a mirror would destroy)
            g = 1 + 0.15 * (torch.rand(len(idx), 1, 1, 1, device=dev) - 0.5)
            x = (x.float() * g).clamp(0, 255)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                lp = predict(norm(x))
            kld, nss, cc = losses(lp.float(), Str[idx], Ftr[idx])
            loss = kld - 0.1 * nss - 0.1 * cc
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
        m = evaluate(Xva, Sva, Fva)
        score = m["kld"] - 0.1 * m["nss"] - 0.1 * m["cc"]
        print(f"epoch {ep:2d}", {k: round(v, 4) for k, v in m.items()}, f"{time.time() - t0:.0f}s", flush=True)
        if best is None or score < best:
            best, best_ep = score, ep
            torch.save(model.state_dict(), ROOT / "ui_unisal_best.pth")
        elif ep - best_ep >= patience:
            print("early stop")
            break
    model.load_state_dict(torch.load(ROOT / "ui_unisal_best.pth", map_location=dev))
    final = {"test": evaluate(Xte, Ste, Fte), "test_web": evaluate(Xtw, Stw, Ftw), "val": evaluate(Xva, Sva, Fva)}
    print("fine-tuned  ", {s: {k: round(v, 4) for k, v in m.items()} for s, m in final.items()}, "best epoch", best_ep)
    json.dump({"pretrained": base, "finetuned": final, "best_epoch": best_ep, "train": len(Xtr), "val": len(Xva), "test": len(Xte), "test_web": len(Xtw),
               "size": [H, W]}, open(ROOT / "metrics.json", "w"), indent=1)
    print(f"TRAIN_OK {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
