Each clip should be short (15-30s), clearly depict one hazard, and be
license-safe to keep in a public repo (Creative Commons / public domain, or
self-recorded). Source from Pexels/Pixabay (CC0 warehouse/forklift footage)
or self-record a short clip with a phone, trimmed with:

    ffmpeg -i raw.mp4 -t 20 -c copy clip.mp4

Expected filenames (referenced by `docs/superpowers/demo-script.md`):

| File | Hazard depicted | Source |
|---|---|---|
| `ppe.mp4` | Person without hard hat / hi-vis vest in a PPE zone | [Pixabay 299813](https://pixabay.com/videos/construction-worker-299813/) |
| `zone_intrusion.mp4` | Person entering a marked restricted zone | [Pixabay 43658](https://pixabay.com/videos/amazon-box-parcels-warehouse-post-43658/) |
| `forklift_proximity.mp4` | Forklift and pedestrian in close proximity | [Pixabay 209883](https://pixabay.com/videos/forklift-machinery-loading-209883/) |
| `fall.mp4` | Person falling / lying on the ground, not moving | [Pixabay 729](https://pixabay.com/videos/sleeping-man-person-alarm-clock-729/) |
| `spill.mp4` | Liquid spill or obstruction blocking a walkway | [Pixabay 15721](https://pixabay.com/videos/water-fluid-simulation-sim-pour-15721/) |

All clips downloaded at Pixabay's `_tiny` resolution to keep the repo light.

**Known gap — `fall.mp4`:** there's no good CC0 stock clip of a person
collapsed/down on a warehouse floor. The current file is a person lying in
bed, which won't realistically trigger VSS's fall/man-down alert rule. Swap
it for a self-recorded clip (someone lying still on a floor, viewed from a
fixed overhead-ish angle) before relying on this hazard in a real demo.
