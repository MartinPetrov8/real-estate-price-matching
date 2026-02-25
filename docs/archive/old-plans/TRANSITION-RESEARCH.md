# Video Transition Research: Smart Motion for Real Estate Videos

**Research Date:** 2026-02-24  
**Context:** alo.bg property listings → TikTok/Instagram 9:16 videos (30-40s)  
**Current Tech:** ffmpeg zoompan (Ken Burns) + xfade (0.25s) between 3s clips + ElevenLabs TTS  
**Key Constraint:** NO generative AI that invents new content. Only enhance existing photos.

---

## 🎯 EXECUTIVE SUMMARY

**Best bet for this pipeline: OpenCV Saliency + 3D Ken Burns + Selective xfade**

1. **Replace dumb center-zoom with saliency-guided Ken Burns** → OpenCV spectral residual (built-in, fast, no hallucination)
2. **Add depth-based parallax** → 3D Ken Burns Effect (sniklaus/3d-ken-burns) for wow factor on hero shots
3. **Upgrade transitions** → Use fadeblack/dissolve for most; circleopen for room changes; avoid gimmicky wipes

**Skip frame interpolation** — RIFE/FILM work great for video (similar frames) but struggle with completely different room photos. Optical flow gets confused when scene changes entirely (bedroom → kitchen). Not worth the complexity for this use case.

---

## 1. SUBJECT-AWARE KEN BURNS

### Problem
Current Ken Burns always zooms from center. But rooms have focal points: a living room's couch, a bedroom's bed, an exterior's entrance. Dumb center-zoom often misses the interesting part.

### Solution: OpenCV Saliency Detection

#### **OpenCV Spectral Residual Saliency**
- **What it does:** Detects "attention-grabbing" regions in a photo using frequency domain analysis
- **GitHub:** Built into OpenCV (`cv2.saliency.StaticSaliencySpectralResidual_create()`)
- **Install:** `pip install opencv-python opencv-contrib-python`
- **How it works:**
  1. Analyze photo with spectral residual algorithm
  2. Generate saliency map (heatmap of interesting regions)
  3. Find centroid of highest-saliency area
  4. Use that as zoom target instead of image center
- **Hallucination risk:** **NONE** — purely analytical, no generation
- **Speed:** Real-time (< 100ms per image on CPU)
- **Fit for pipeline:** **EXCELLENT** — drop-in replacement for current zoompan logic

**Code example:**
```python
import cv2
img = cv2.imread('room.jpg')
saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
success, saliency_map = saliency.computeSaliency(img)
# Find brightest region → that's your zoom target
```

**References:**
- PyImageSearch tutorial: https://pyimagesearch.com/2018/07/16/opencv-saliency-detection/
- GitHub examples: https://github.com/ivanred6/image_saliency_opencv

#### **Alternative: OpenCV Fine-Grained Saliency**
- Similar but uses objectness estimation (BING algorithm)
- Slower, slightly more accurate for object-heavy scenes
- Probably overkill for real estate interiors

**Recommendation:** Use Spectral Residual for speed. If results aren't good, try Fine-Grained.

---

## 2. FRAME INTERPOLATION (Photo A → Photo B Morphing)

### Tools Evaluated

#### **RIFE (Real-Time Intermediate Flow Estimation)**
- **GitHub:** https://github.com/hzwer/ECCV2022-RIFE (official) / https://github.com/hzwer/Practical-RIFE (production-ready)
- **Install:** 
  ```bash
  git clone https://github.com/hzwer/Practical-RIFE
  cd Practical-RIFE
  pip install -r requirements.txt
  ```
- **What it does:** Uses optical flow neural network (IFNet) to estimate intermediate frames between two images
- **Hallucination risk:** **LOW-MEDIUM** — doesn't generate new content, but blends/warps existing pixels. Can create artifacts when scenes differ drastically
- **Speed:** Real-time (60fps interpolation on RTX GPU)
- **Latest version:** v4.24+ (2024.08) — optimized for diffusion model outputs
- **Fit for pipeline:** **POOR for room-to-room transitions**
  - ✅ Works great: Kitchen angle 1 → kitchen angle 2 (same room, slight camera move)
  - ❌ Struggles: Bedroom → kitchen (completely different scenes)
  - Optical flow assumes pixel correspondence. When entire scene changes, it creates weird morphing artifacts

**Use case:** ONLY if you have multiple photos of the SAME room and want ultra-smooth pan between them. Not for typical 7-8 different rooms.

#### **FILM (Google Frame Interpolation for Large Motion)**
- **GitHub:** https://github.com/google-research/frame-interpolation (official TensorFlow) / https://github.com/dajes/frame-interpolation-pytorch (PyTorch port)
- **Install:** 
  ```bash
  # PyTorch version (easier)
  pip install film-pytorch
  # Or clone official
  git clone https://github.com/google-research/frame-interpolation
  ```
- **What it does:** Specialized for large motion (camera pans, object movement). Better than RIFE for big scene changes
- **Hallucination risk:** **LOW-MEDIUM** — same as RIFE, warps existing pixels
- **Speed:** Slower than RIFE (~5-10 fps on RTX GPU)
- **Fit for pipeline:** **MARGINAL**
  - Better than RIFE for different scenes, but still expects some visual continuity
  - Not designed for bedroom → kitchen jumps
  - Google trained it for "large motion within a scene," not "completely different scenes"

**Verdict:** Better than RIFE but still not ideal for real estate where every photo is a different room.

#### **DAIN (Depth-Aware Video Frame Interpolation)**
- **GitHub:** https://github.com/baowenbo/DAIN
- **Install:** Complex (requires PyTorch 1.0.0, custom CUDA layers)
- **What it does:** Adds depth awareness to frame interpolation
- **Hallucination risk:** **LOW-MEDIUM**
- **Speed:** Slow (research code, not optimized)
- **Fit for pipeline:** **POOR** — outdated (2019), hard to install, RIFE/FILM are better

**Verdict:** Skip. Superseded by RIFE and FILM.

#### **ffmpeg minterpolate (built-in optical flow)**
- **Install:** Already in ffmpeg
- **Command:** 
  ```bash
  ffmpeg -i input.mp4 -vf "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" output.mp4
  ```
- **What it does:** Motion-compensated frame interpolation using built-in optical flow
- **Hallucination risk:** **NONE** (pure interpolation, no AI)
- **Speed:** Slow on CPU, no GPU acceleration
- **Fit for pipeline:** **VERY POOR**
  - Works for upscaling video framerate (30fps → 60fps)
  - Terrible for interpolating between completely different photos
  - Creates ghosting/artifacts when scene changes

**Verdict:** Skip. Only useful for video framerate conversion, not photo transitions.

#### **Flowframes (RIFE GUI wrapper)**
- **GitHub:** https://github.com/n00mkrad/flowframes
- **Install:** Windows GUI app (has CLI mode)
- **What it does:** User-friendly wrapper around RIFE/DAIN
- **Fit for pipeline:** **N/A** — this is a GUI tool, not a library
- **Note:** If you want to test RIFE manually on sample photos, Flowframes is the easiest way

---

### Frame Interpolation: Final Verdict

**Do NOT use frame interpolation for this pipeline.**

**Why:**
- Real estate videos jump between completely different rooms (bedroom → bathroom → kitchen → exterior)
- Optical flow interpolation assumes visual continuity (similar backgrounds, moving objects, camera pans)
- When you interpolate bedroom → kitchen, you get weird morphing artifacts — walls blend into cabinets, beds morph into countertops
- **Result looks worse than a clean cut or dissolve transition**

**When frame interpolation WOULD work:**
- Multiple photos of the same room from slightly different angles
- Exterior shots panning across a building facade
- Walkthrough videos where scenes gradually change

**For typical alo.bg listings (7-8 different room photos):** Stick with xfade transitions. They look cleaner.

---

## 3. DEPTH-BASED PARALLAX (2.5D Photo Animation)

### **3D Ken Burns Effect**
- **GitHub:** https://github.com/sniklaus/3d-ken-burns (original) / https://github.com/downysoftware/3D-Ken-Burns-MEGA (batch processing fork)
- **What it does:** 
  1. Estimate depth map from single photo using neural network
  2. Separate image into depth layers
  3. Animate with parallax motion (foreground moves faster than background)
  4. Inpaint exposed areas (fills gaps behind objects)
- **Install:**
  ```bash
  git clone https://github.com/sniklaus/3d-ken-burns
  cd 3d-ken-burns
  pip install torch torchvision
  pip install moviepy
  ```
- **Hallucination risk:** **LOW-MEDIUM**
  - Depth estimation: No hallucination (MiDaS-based)
  - Inpainting: **MEDIUM** — fills gaps when camera "moves past" objects. Uses neural inpainting (may invent textures)
  - Mitigation: Use subtle zoom/pan to minimize exposed areas
- **Speed:** ~30-60s per image on GPU (generates 5-10s of video)
- **Output quality:** High. Creates cinematic parallax effect.
- **Fit for pipeline:** **GOOD for hero shots**
  - Use on 1-2 standout photos per video (living room, exterior)
  - Too slow to apply to all 7-8 photos
  - Dramatic effect — use sparingly or it becomes gimmicky

**Recommendation:** 
- Apply 3D Ken Burns to the first photo (exterior or main living space) for impact
- Use regular saliency-guided Ken Burns for the rest
- Or skip entirely if processing speed matters more than wow factor

### **MiDaS Depth Estimation (standalone)**
- **GitHub:** https://github.com/isl-org/MiDaS
- **What it does:** Just generates depth maps (grayscale image where brightness = distance from camera)
- **Install:** `pip install timm` + download model weights
- **Hallucination risk:** **NONE** (pure depth estimation)
- **Fit for pipeline:** **BUILD YOUR OWN**
  - MiDaS gives you depth map
  - You'd need to write code to separate layers + animate parallax
  - 3D Ken Burns already does this for you

**Verdict:** Use 3D Ken Burns (includes MiDaS + layer separation + animation). Don't reinvent the wheel.

### **Depth Anything v2**
- **GitHub:** https://github.com/DepthAnything/Depth-Anything-V2
- **What it does:** Newer (2024), faster, more accurate depth estimation than MiDaS
- **Install:**
  ```bash
  git clone https://github.com/DepthAnything/Depth-Anything-V2
  cd Depth-Anything-V2
  pip install -r requirements.txt
  ```
- **Speed:** 2-3x faster than MiDaS
- **Hallucination risk:** **NONE**
- **Fit for pipeline:** **FUTURE UPGRADE**
  - If you build custom parallax pipeline, use Depth Anything v2 instead of MiDaS
  - 3D Ken Burns currently uses MiDaS (2020 tech)
  - Could fork 3D Ken Burns and swap in Depth Anything v2 for speed boost

**Verdict:** Keep an eye on this. If someone creates "3D Ken Burns v2" with Depth Anything, it'll be faster.

### **Parallax-Maker**
- **GitHub:** https://github.com/provos/parallax-maker
- **What it does:** Generates 2.5D images for parallax scrolling effects (web/mobile)
- **Install:** Uses MiDaS or DINOv2 for depth
- **Fit for pipeline:** **WRONG USE CASE**
  - Designed for static parallax (user tilts phone, image shifts)
  - Not for video animation

**Verdict:** Skip. Use 3D Ken Burns for video.

---

## 4. FFMPEG XFADE TRANSITION CATALOGUE

ffmpeg has **44 built-in transition types**. Not all are suitable for professional real estate videos.

### Full List:
custom, fade, wipeleft, wiperight, wipeup, wipedown, slideleft, slideright, slideup, slidedown, circlecrop, rectcrop, distance, fadeblack, fadewhite, radial, smoothleft, smoothright, smoothup, smoothdown, circleopen, circleclose, vertopen, vertclose, horzopen, horzclose, dissolve, pixelize, diagtl, diagtr, diagbl, diagbr, hlslice, hrslice, vuslice, vdslice, hblur, fadegrays, wipetl, wipetr, wipebl, wipebr, squeezeh, squeezev

### ✅ TOP 5 FOR REAL ESTATE (PROFESSIONAL LOOK)

#### **1. dissolve** (Classic Cross-Dissolve)
- **What it does:** Smooth fade from A to B (transparency blending)
- **Best for:** Any transition. Safe default.
- **Feel:** Clean, professional, timeless
- **When to use:** Bedroom → bathroom, kitchen → dining room (similar spaces)

#### **2. fadeblack** (Fade Through Black)
- **What it does:** Fade to black, then fade in next image
- **Best for:** Major scene changes (interior → exterior, day → night)
- **Feel:** Elegant pause, signals "new chapter"
- **When to use:** Living room → exterior, last interior → property exterior

#### **3. fadegrays** (Fade Through Gray)
- **What it does:** Like fadeblack but through neutral gray
- **Best for:** Softer version of fadeblack
- **Feel:** Modern, less dramatic
- **When to use:** Same as fadeblack when black feels too heavy

#### **4. circleopen** (Iris Open)
- **What it does:** Next image reveals from center circle expanding outward
- **Best for:** Transitioning to a "reveal" shot (main living space, master bedroom)
- **Feel:** Emphasizes what's coming next
- **When to use:** Exterior → interior entrance, hallway → hero room
- **Warning:** Can feel gimmicky if overused. Once per video max.

#### **5. smoothleft / smoothright** (Smooth Wipe)
- **What it does:** Gentle horizontal wipe with soft edge
- **Best for:** Room-to-room transitions on same floor
- **Feel:** Spatial continuity (implies movement through space)
- **When to use:** Kitchen → dining room, bedroom → ensuite bathroom
- **Direction:** Use `smoothright` for forward flow, `smoothleft` for backtracking

### ❌ AVOID (TOO GIMMICKY FOR REAL ESTATE)

- **pixelize** — looks like a Minecraft transition
- **squeezeh / squeezev** — cheesy video-editing-101 effect
- **diagtl / diagtr / diagbl / diagbr** — diagonal wipes scream "2005 PowerPoint"
- **hlslice / hrslice / vuslice / vdslice** — venetian blind effects (yikes)
- **rectcrop / circlecrop** — crop transitions feel claustrophobic
- **distance** — weird "push apart" effect

### 🤔 MAYBE (CONTEXT-DEPENDENT)

- **slideright / slideleft** — Hard cut slide. Can work for montage-style pacing but feels fast
- **radial** — Circular wipe. Less elegant than circleopen but could work for creative videos
- **hblur** — Blur transition. Interesting but can look like a camera focus mistake

---

### Recommended Transition Strategy:

**For typical 7-photo property video:**

1. Photo 1 (exterior) → Photo 2 (entrance): **fadeblack** (arriving at property)
2. Photo 2 (entrance) → Photo 3 (living room): **circleopen** (reveal hero space)
3. Photo 3 (living room) → Photo 4 (kitchen): **dissolve** (adjacent spaces)
4. Photo 4 (kitchen) → Photo 5 (bedroom): **dissolve** (standard transition)
5. Photo 5 (bedroom) → Photo 6 (bathroom): **smoothright** (ensuite flow)
6. Photo 6 (bathroom) → Photo 7 (exterior/balcony): **fadeblack** (back to exterior)

**Pattern:**
- Use **fadeblack** for major scene changes
- Use **dissolve** as workhorse transition
- Use **circleopen** once for emphasis
- Use **smooth wipes** for spatial continuity when relevant

**Pacing:** Keep all transitions at 0.25-0.5s. Longer than 0.5s drags; shorter than 0.25s feels jarring.

---

## 5. OTHER TOOLS EVALUATED

### ❌ **Stable Video Diffusion (Stability AI)**
- **Status:** REJECTED — GENERATIVE AI
- **Why:** This is a video generation model. It *creates* new frames by inventing content.
- **Hallucination risk:** **EXTREME** — it's literally designed to hallucinate motion
- **Verdict:** Violates "no generation" constraint. Do not use.

### ❌ **Runway Gen-2, Kling, fal.ai WAN 2.1**
- **Status:** Already rejected in task brief
- **Why:** All generative video models (text/image → video)
- **Verdict:** Not evaluated. Out of scope.

### ⚠️ **PyTTI-Tools (FILM wrapper)**
- **GitHub:** Various wrappers for FILM interpolation
- **Status:** Same limitations as FILM — doesn't solve the "different rooms" problem
- **Verdict:** No advantage over direct FILM usage.

---

## 📊 IMPLEMENTATION PRIORITY

### Phase 1: Quick Wins (Week 1)
✅ **Upgrade transitions:** Test xfade types, replace current 0.25s xfade with strategic transitions  
✅ **Add saliency-guided zoom:** Integrate OpenCV spectral residual → detect zoom targets  
**Effort:** Low (few hours)  
**Impact:** Medium-High (noticeably better framing + more professional transitions)

### Phase 2: Premium Feature (Week 2-3)
⚠️ **3D Ken Burns on hero shots:** Apply parallax effect to 1-2 key photos per video  
**Effort:** Medium (need to integrate sniklaus/3d-ken-burns, handle inpainting artifacts)  
**Impact:** High (dramatic wow factor)  
**Trade-off:** Adds 30-60s processing time per hero shot

### Phase 3: Experimental (If Time / If Needed)
❓ **Frame interpolation for same-room sequences:** Only if listings have multiple angles of same room  
**Effort:** Medium (RIFE integration)  
**Impact:** Low-Medium (rare use case)  
**Decision:** Evaluate after Phase 1/2. Probably not worth it.

---

## 🎬 RECOMMENDED PIPELINE V2

```
FOR EACH PHOTO:
  1. Run OpenCV spectral residual saliency detection
  2. Find centroid of highest-saliency region
  3. Generate Ken Burns zoom path: start at saliency center, zoom out slightly OR
     start zoomed out, zoom into saliency center
  
  IF photo is_hero_shot (first/last or main living space):
    4a. Run 3D Ken Burns (parallax animation)
  ELSE:
    4b. Run standard ffmpeg zoompan with saliency target
  
  5. Apply transition:
     - fadeblack: major scene changes (exterior ↔ interior)
     - circleopen: once per video for hero reveal
     - dissolve: default for most transitions
     - smoothleft/right: adjacent rooms with spatial flow
```

**Processing time estimate:**
- Standard path (saliency + zoompan): ~0.5s per photo
- 3D Ken Burns path: ~40s per photo
- Total for 7 photos (1 hero, 6 standard): ~43s (vs ~3.5s currently)

**Worth it?** If videos are generated in batches overnight, yes. If real-time is critical, use Phase 1 only (saliency + smart transitions).

---

## 🔗 RESOURCES

### Essential GitHub Repos
- OpenCV Saliency: https://github.com/ivanred6/image_saliency_opencv
- 3D Ken Burns: https://github.com/sniklaus/3d-ken-burns
- RIFE (if needed later): https://github.com/hzwer/Practical-RIFE
- FILM (if needed later): https://github.com/google-research/frame-interpolation
- Depth Anything v2: https://github.com/DepthAnything/Depth-Anything-V2

### Useful Tutorials
- PyImageSearch OpenCV Saliency: https://pyimagesearch.com/2018/07/16/opencv-saliency-detection/
- ffmpeg xfade examples: https://ottverse.com/crossfade-between-videos-ffmpeg-xfade-filter/
- 3D Ken Burns paper: https://arxiv.org/abs/1909.05483

### Alternative Tools (Not Recommended But Exist)
- Flowframes GUI: https://nmkd.itch.io/flowframes (for manual testing)
- xfade-easing (custom transitions): https://github.com/scriptituk/xfade-easing

---

## 🚫 WHAT NOT TO USE

| Tool | Reason |
|------|--------|
| Stable Video Diffusion | Generative AI — invents content |
| Runway Gen-2 | Generative AI — invents content |
| Kling | Generative AI — invents content |
| fal.ai WAN 2.1 | Generative AI — invents content |
| DAIN | Outdated, hard to install, superseded by RIFE |
| ffmpeg minterpolate | Only good for video framerate upscaling, not photo transitions |

---

## ✅ FINAL RECOMMENDATION

**Do this:**
1. ✅ Add OpenCV saliency detection → intelligent zoom targets
2. ✅ Upgrade xfade strategy → fadeblack/dissolve/circleopen based on context
3. ⚠️ Consider 3D Ken Burns for 1 hero shot per video (if processing time allows)

**Don't do this:**
- ❌ Frame interpolation between different rooms (RIFE/FILM) — creates artifacts
- ❌ Any generative AI models — violates constraint

**Result:** Professional-looking videos with smart framing and cinematic transitions, all using existing photo content only.
