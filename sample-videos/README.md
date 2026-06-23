Each clip should be short (15-30s), clearly depict one hazard, and be
license-safe to keep in a public repo (Creative Commons / public domain, or
self-recorded). Source from Pexels/Pixabay (CC0 warehouse/forklift footage)
or self-record a short clip with a phone, trimmed with:

    ffmpeg -i raw.mp4 -t 20 -c copy clip.mp4

Expected filenames (referenced by `docs/superpowers/demo-script.md`):

| File | Hazard depicted | Source |
|---|---|---|
| `ppe.mp4` | Person without hard hat / hi-vis vest in a PPE zone | NVIDIA PhysicalAI SDG-Warehouse (`warehouse_box_pickup`, run 8) |
| `zone_intrusion.mp4` | Person entering a marked restricted zone | NVIDIA PhysicalAI SDG-Warehouse (`warehouse_fire`, run 6) |
| `forklift_proximity.mp4` | Forklift and pedestrian in close proximity | NVIDIA PhysicalAI SDG-Warehouse (`forklift_human_nearmiss`, run 1) |
| `fall.mp4` | Person falling / lying on the ground, not moving | [Pixabay 729](https://pixabay.com/videos/sleeping-man-person-alarm-clock-729/) |
| `spill.mp4` | Liquid spill or obstruction blocking a walkway | NVIDIA PhysicalAI SDG-Warehouse (`forklift_shelf_collision`, run 5) |

`ppe.mp4`, `zone_intrusion.mp4`, `forklift_proximity.mp4`, and `spill.mp4` are
single ~10-25s clips extracted (via HTTP range request, one WebDataset tar
entry — not a full ~5GB shard download) from
[nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes](https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes)
on Hugging Face (synthetic, Isaac Sim, OpenMDW 1.1 license — commercial use
OK). The dataset's 4 native scenarios (forklift-human near-miss, warehouse
fire/evacuation, forklift-shelf collision, box pickup) don't map 1:1 onto
this app's 5 hazard types, so 3 of the 4 are repurposed by visual similarity
rather than the dataset's own label:

- `forklift_proximity.mp4` — exact match, dataset's native near-miss scenario.
- `ppe.mp4` — repurposed from `warehouse_box_pickup`: worker visible without
  hard hat/hi-vis vest near a forklift in a marked aisle. Not the dataset's
  intended hazard, but a reasonable visual stand-in.
- `zone_intrusion.mp4` — repurposed from `warehouse_fire`: no flames visible
  in this particular clip, but shows a person crossing a cone-marked area —
  decent restricted-zone stand-in, not actually a fire-evacuation depiction.
- `spill.mp4` — weakest repurpose, from `forklift_shelf_collision`: this
  specific 15s clip only shows the forklift and a small box stack, no actual
  collision/knockdown moment. Doesn't strongly depict a spill or obstruction.
  Worth re-extracting a different run/timestamp from the same shard
  (`rgb/forklift_shelf_collision/forklift_collision-rgb-00000.tar`) if a
  clearer collision moment is needed.

**Known gap — `fall.mp4`:** there's no good CC0 stock clip of a person
collapsed/down on a warehouse floor, and the NVIDIA dataset above has no
fall/man-down scenario either. The current file is a person lying in bed,
which won't realistically trigger VSS's fall/man-down alert rule. Swap it
for a self-recorded clip (someone lying still on a floor, viewed from a
fixed overhead-ish angle) before relying on this hazard in a real demo.
