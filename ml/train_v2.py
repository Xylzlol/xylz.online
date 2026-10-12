"""A stronger UI saliency model, scored on exactly the same held-out pages and with exactly the same
metric code as the shipped one (train_ui.py), image by image, so the comparison is paired.

  python train_v2.py baseline        per-image test scores of the shipped UNISAL fine-tune
  python train_v2.py train NAME ...  train a DINOv2-backbone model, write its per-image test scores

Model: a DINOv2 ViT (timm) reads the screenshot at 448 x 672 (32 x 48 patches); features from four
depths are fused by a small convolutional decoder into a log-probability map at 288 x 448, plus a
learned prior per UI type (web, desktop, mobile, poster). Trained on every UEyes type; the official
test split (web + desktop, the same 54 pages as the baseline) is never seen until the end.
"""
import csv, json, math, os, sys, time, types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

ROOT = Path(__file__).parent
os.environ.setdefault("HF_HOME", str(ROOT / "hf"))
_pkg = types.ModuleType("unisal"); _pkg.__path__ = [str(ROOT / "unisal" / "unisal")]; sys.modules["unisal"] = _pkg
from unisal import utils as U  # noqa: E402

DATA = ROOT / "data" / "UEyes_dataset"
H, W = 288, 448            # target maps, as the baseline
VH, VW = 448, 672          # what the ViT reads
TYPES = ["web", "desktop", "mobile", "poster"]
dev = torch.device("cuda")
torch.backends.cudnn.benchmark = True
torch.backends.cuda.matmul.allow_tf32 = True


def rows():
    out = []
    for r in csv.DictReader(open(DATA / "image_types.csv", encoding="utf-8-sig"), delimiter=";"):
        out.append((r["Image Name"].strip(), r["Category"].strip().lower(), r["Train/Test"].strip().lower()))
    return out


def load(name, size):
    stem = Path(name).stem
    img = next((p for p in (DATA / "images").glob(stem + ".*")), None)
    hm = DATA / "saliency_maps" / "heatmaps_3s" / (stem + ".png")
    fx = DATA / "saliency_maps" / "fixmaps_3s" / (stem + ".png")
    if not (img and hm.exists() and fx.exists()):
        hm = next((p for p in (DATA / "saliency_maps" / "heatmaps_3s").glob(stem + ".*")), None)
        fx = next((p for p in (DATA / "saliency_maps" / "fixmaps_3s").glob(stem + ".*")), None)
        if not (img and hm and fx):
            return None
    im = np.asarray(Image.open(img).convert("RGB").resize((size[1], size[0]), Image.BICUBIC), dtype=np.uint8)
    sal = np.asarray(Image.open(hm).convert("L").resize((W, H), Image.BILINEAR), dtype=np.uint8)
    fix = torch.from_numpy(np.asarray(Image.open(fx).convert("L"), dtype=np.uint8) > 0).float()[None, None]
    fix = F.adaptive_max_pool2d(fix, (H, W))[0, 0].to(torch.uint8).numpy()
    return im, sal, fix


def dataset(size):
    rs = [r for r in rows() if r[1] in TYPES]
    with ThreadPoolExecutor(16) as ex:
        got = list(ex.map(lambda r: (r, load(r[0], size)), rs))
    got = [(r, d) for r, d in got if d is not None]
    test = [(r, d) for r, d in got if "test" in r[2] and r[1] in ("web", "desktop")]
    pool = [(r, d) for r, d in got if "test" not in r[2]]
    return pool, test


def to_gpu(items):
    X = torch.from_numpy(np.stack([d[0] for _, d in items])).permute(0, 3, 1, 2).contiguous().to(dev)
    S = torch.from_numpy(np.stack([d[1] for _, d in items]))[:, None].to(dev)
    Fx = torch.from_numpy(np.stack([d[2] for _, d in items]))[:, None].to(dev)
    T = torch.tensor([TYPES.index(r[1]) for r, _ in items], device=dev)
    return X, S, Fx, T


MEAN = torch.tensor([0.485, 0.456, 0.406], device=dev).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225], device=dev).view(1, 3, 1, 1)
norm = lambda x: ((x.float() / 255 - MEAN) / STD).contiguous(memory_format=torch.channels_last)


def per_image(logp, sal, fix):
    """the baseline's own metric code (train_ui.losses), per image: kld, nss, cc"""
    sal = sal.float()
    sal = sal / sal.flatten(1).sum(1).clamp_min(1e-8).view(-1, 1, 1, 1)
    kld = U.kld_loss(logp[:, None], sal[:, None])
    nss = U.nss(logp[:, None].exp(), fix[:, None].bool())
    cc = U.corr_coeff(logp[:, None].exp(), sal[:, None])
    return kld.flatten(), nss.flatten(), cc.flatten()


def score(predict, X, S, Fx, T, bs=16):
    out = []
    with torch.no_grad():
        for i in range(0, len(X), bs):
            with torch.autocast("cuda", dtype=torch.bfloat16):
                lp = predict(X[i:i + bs], T[i:i + bs])
            k, n, c = per_image(lp.float(), S[i:i + bs], Fx[i:i + bs])
            out += [{"kld": float(a), "nss": float(b), "cc": float(d)} for a, b, d in zip(k, n, c)]
    return out


def summary(per, names, cats):
    res = {}
    for sub in ("all", "web"):
        idx = [i for i, c in enumerate(cats) if sub == "all" or c == sub]
        res[sub] = {m: float(np.mean([per[i][m] for i in idx])) for m in ("cc", "nss", "kld")}
    return res


# ---------------- the baseline ----------------

def baseline():
    from unisal.model import UNISAL
    pool, test = dataset((H, W))
    X, S, Fx, T = to_gpu(test)
    cfg = json.load(open(ROOT / "unisal/training_runs/pretrained_unisal/UNISAL.json"))
    cfg["cnn_cfg"]["pretrained"] = False; cfg.pop("verbose", None)
    model = UNISAL(**cfg).to(dev).to(memory_format=torch.channels_last).eval()
    model.load_state_dict(torch.load(ROOT / "ui_unisal_best.pth", map_location=dev))
    per = score(lambda x, t: model(norm(x)[:, None], source="SALICON", static=True)[:, 0], X, S, Fx, T)
    names = [r[0] for r, _ in test]; cats = [r[1] for r, _ in test]
    json.dump({"names": names, "cats": cats, "per": per, "summary": summary(per, names, cats)},
              open(ROOT / "runs" / "baseline.json", "w"), indent=1)
    print("baseline", summary(per, names, cats))


# ---------------- the new model ----------------

class Sal(nn.Module):
    def __init__(self, backbone="vit_base_patch14_dinov2.lvd142m", depths=(2, 5, 8, 11), dim=192):
        super().__init__()
        import timm
        self.vit = timm.create_model(backbone, pretrained=True, num_classes=0, dynamic_img_size=True)
        self.depths = list(depths)
        c = self.vit.embed_dim
        self.proj = nn.ModuleList([nn.Sequential(nn.Conv2d(c, dim, 1), nn.GroupNorm(8, dim), nn.GELU()) for _ in depths])
        self.fuse = nn.Sequential(nn.Conv2d(dim * len(depths), 256, 3, padding=1), nn.GroupNorm(16, 256), nn.GELU())
        self.up1 = nn.Sequential(nn.Conv2d(256, 128, 3, padding=1), nn.GroupNorm(8, 128), nn.GELU())
        self.up2 = nn.Sequential(nn.Conv2d(128, 64, 3, padding=1), nn.GroupNorm(8, 64), nn.GELU())
        self.out = nn.Conv2d(64, 1, 3, padding=1)
        # a learned log-prior per UI type (centre and reading biases), low resolution, upsampled
        self.prior = nn.Parameter(torch.zeros(len(TYPES), 1, 18, 28))
        self.prior_w = nn.Parameter(torch.tensor(1.0))

    def forward(self, x, t):
        feats = self.vit.forward_intermediates(x, indices=self.depths, intermediates_only=True)
        f = torch.cat([p(z) for p, z in zip(self.proj, feats)], 1)
        f = self.fuse(f)
        f = self.up1(F.interpolate(f, scale_factor=2, mode="bilinear", align_corners=False))
        f = self.up2(F.interpolate(f, scale_factor=2, mode="bilinear", align_corners=False))
        z = F.interpolate(self.out(f), size=(H, W), mode="bilinear", align_corners=False)
        z = z + self.prior_w * F.interpolate(self.prior[t], size=(H, W), mode="bilinear", align_corners=False)
        return F.log_softmax(z.float().flatten(1), 1).view(-1, 1, H, W)


def train(name, backbone="vit_base_patch14_dinov2.lvd142m", epochs=24, bs=8, lr_b=2e-5, lr_h=4e-4, types_train=TYPES, seed=0):
    torch.manual_seed(seed); np.random.seed(seed)
    t0 = time.time()
    pool, test = dataset((VH, VW))
    pool = [(r, d) for r, d in pool if r[1] in types_train]
    rng = np.random.RandomState(0)
    order = rng.permutation(len(pool))
    nval = len(pool) // 10
    va = [pool[i] for i in order[:nval]]
    tr = [pool[i] for i in order[nval:]]
    va_wd = [(r, d) for r, d in va if r[1] in ("web", "desktop")]  # model selection on the test's own types
    print(f"{name}: train {len(tr)}  val {len(va_wd)} (web+desktop of {len(va)})  test {len(test)}  loaded {time.time() - t0:.0f}s", flush=True)
    Xtr, Str, Ftr, Ttr = to_gpu(tr)
    Xva, Sva, Fva, Tva = to_gpu(va_wd)
    Xte, Ste, Fte, Tte = to_gpu(test)

    model = Sal(backbone).to(dev).to(memory_format=torch.channels_last)
    head = [p for n, p in model.named_parameters() if not n.startswith("vit.")]
    opt = torch.optim.AdamW([{"params": model.vit.parameters(), "lr": lr_b}, {"params": head, "lr": lr_h}], weight_decay=0.05)
    steps = epochs * math.ceil(len(Xtr) / bs)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[lr_b, lr_h], total_steps=steps, pct_start=0.1)
    pred = lambda x, t: model(norm(x), t)
    best, best_ep, patience = None, -1, 6
    ckpt = ROOT / "runs" / f"{name}.pth"
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(Xtr), device=dev)
        for i in range(0, len(perm), bs):
            idx = perm[i:i + bs]
            g = 1 + 0.15 * (torch.rand(len(idx), 1, 1, 1, device=dev) - 0.5)
            x = (Xtr[idx].float() * g).clamp(0, 255)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                lp = pred(x, Ttr[idx])
            k, n, c = per_image(lp.float(), Str[idx], Ftr[idx])
            loss = k.mean() - 0.1 * n.mean() - 0.1 * c.mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step()
        model.eval()
        pv = score(pred, Xva, Sva, Fva, Tva)
        m = {k_: float(np.mean([p[k_] for p in pv])) for k_ in ("kld", "nss", "cc")}
        sc = m["kld"] - 0.1 * m["nss"] - 0.1 * m["cc"]
        print(f"{name} epoch {ep:2d} val cc {m['cc']:.4f} nss {m['nss']:.3f} kld {m['kld']:.4f}  {time.time() - t0:.0f}s", flush=True)
        if best is None or sc < best:
            best, best_ep = sc, ep
            torch.save(model.state_dict(), ckpt)
        elif ep - best_ep >= patience:
            break
    model.load_state_dict(torch.load(ckpt, map_location=dev)); model.eval()
    per = score(pred, Xte, Ste, Fte, Tte)
    names = [r[0] for r, _ in test]; cats = [r[1] for r, _ in test]
    res = {"names": names, "cats": cats, "per": per, "summary": summary(per, names, cats), "best_epoch": best_ep,
           "config": {"backbone": backbone, "epochs": epochs, "bs": bs, "lr_b": lr_b, "lr_h": lr_h, "types": types_train, "seed": seed},
           "seconds": round(time.time() - t0)}
    json.dump(res, open(ROOT / "runs" / f"{name}.json", "w"), indent=1)
    print(f"{name} TEST", res["summary"], "best epoch", best_ep, f"{res['seconds']}s", flush=True)


if __name__ == "__main__":
    (ROOT / "runs").mkdir(exist_ok=True)
    if sys.argv[1] == "baseline":
        baseline()
    else:
        kw = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        train(sys.argv[2], **kw)
