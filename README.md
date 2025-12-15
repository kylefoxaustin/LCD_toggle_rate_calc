# LCD Toggle Activity Calculator

A command-line tool for modeling GPIO toggle rates on parallel LCD interfaces. Useful for reliability analysis, power estimation, and EMI characterization of embedded display systems.

## Overview

When driving an LCD via a parallel RGB interface (8/16/18/24-bit), the GPIO pins toggle at rates determined by:
- Display resolution and refresh rate
- Pixel clock frequency
- Content activity (how much of the screen changes frame-to-frame)

This tool calculates toggle rates and projects lifetime totals, helping you answer questions like:
- "How many toggle cycles will my GPIO pins accumulate over 10 years?"
- "What's the worst-case toggle rate for full-motion video?"
- "How does a static dashboard compare to dynamic content?"

## Installation

```bash
git clone https://github.com/kylefoxaustin/LCD_toggle_rate_calc.git
cd LCD_toggle_rate_calc
chmod +x lcd_toggle_calc.py
```

No external dependencies - uses Python 3.7+ standard library only.

## Quick Start

```bash
# Using presets (easiest)
./lcd_toggle_calc.py --preset 1080p60 --content desktop

# Custom display parameters
./lcd_toggle_calc.py --H 800 --V 480 --fp 33.3 --fr 60

# Verbose output with all details
./lcd_toggle_calc.py --preset wvga --content static -v

# List all available presets
./lcd_toggle_calc.py --list-presets
```

## Content Activity Model

The tool models screen content using up to 3 regions. This lets you represent realistic mixed-content scenarios like a dashboard with both static and animated elements.

### Region Parameters

Each region has three parameters:

| Parameter | Description | Range |
|-----------|-------------|-------|
| `--aN` | Fraction of screen area | 0.0 - 1.0 (must sum to 1.0) |
| `--cN` | Fraction of pixels that change each frame | 0.0 - 1.0 |
| `--hN` | Average bit flips (Hamming distance) per changed pixel | 0 - W (bus width) |

Where N is the region number (1, 2, or 3).

### Understanding the Parameters

**Area fraction (a):** What percentage of the screen does this region cover? A full-screen video would be `a=1.0`, while a small status indicator might be `a=0.05`.

**Change rate (c):** What fraction of pixels in this region change every frame? Static content has `c=0.0`, while video typically has `c=1.0` (every pixel potentially changes). A blinking cursor might have `c=0.01`.

**Hamming distance (h):** When a pixel does change, how many bits flip on average? This depends on the nature of the content:

| h value | Typical content |
|---------|-----------------|
| 0 | No change (static) |
| 2-4 | Subtle changes (anti-aliased text, slight color shifts) |
| 4-6 | Small updates (cursor blink, icon highlights) |
| 6-8 | Moderate changes (scrolling text, UI transitions) |
| 8-12 | Significant changes (video, animation, photos) |
| W (24) | Maximum (complete color inversion, e.g., black ↔ white) |

### Region Examples

**Example 1: Mostly Static Dashboard**

An automotive HMI with 80% static background, 15% slowly-updating gauges, and 5% animated elements:

```bash
./lcd_toggle_calc.py --preset wxga \
    --a1 0.80 --c1 0.0  --h1 0 \
    --a2 0.15 --c2 0.05 --h2 4 \
    --a3 0.05 --c3 1.0  --h3 12
```

Breakdown:
- Region 1: 80% of screen is static (`c=0`, `h=0`)
- Region 2: 15% updates 5% of its pixels per frame with subtle changes (`h=4`)
- Region 3: 5% is fully animated video/graphics (`c=1.0`, `h=12`)

**Example 2: Full-Screen Video Playback**

Every pixel potentially changes every frame:

```bash
./lcd_toggle_calc.py --preset 1080p60 \
    --a1 0.0 --c1 0.0 --h1 0 \
    --a2 0.0 --c2 0.0 --h2 0 \
    --a3 1.0 --c3 1.0 --h3 12
```

**Example 3: Desktop with Active Window**

30% static (desktop background), 50% moderate activity (application windows), 20% high activity (video player):

```bash
./lcd_toggle_calc.py --preset 1080p60 \
    --a1 0.30 --c1 0.0  --h1 0 \
    --a2 0.50 --c2 0.10 --h2 8 \
    --a3 0.20 --c3 1.0  --h3 12
```

**Example 4: Text Terminal**

95% static, 5% cursor line with occasional updates:

```bash
./lcd_toggle_calc.py --preset xga \
    --a1 0.95 --c1 0.0  --h1 0 \
    --a2 0.05 --c2 0.02 --h2 6 \
    --a3 0.0  --c3 0.0  --h3 0
```

**Example 5: Worst Case Analysis**

For reliability margin testing - every bit of every pixel flips every frame:

```bash
./lcd_toggle_calc.py --preset 1080p60 \
    --a1 0.0 --c1 0.0 --h1 0 \
    --a2 0.0 --c2 0.0 --h2 0 \
    --a3 1.0 --c3 1.0 --h3 24
```

### Built-in Content Presets

For convenience, common scenarios are available as presets:

| Preset | Description | Regions |
|--------|-------------|---------|
| `static` | HMI idle, static dashboard | 95% static, 5% minor updates |
| `desktop` | General desktop use | 30% static, 50% moderate, 20% video |
| `video` | Full-screen video playback | 10% moderate, 90% full-motion |
| `worst` | Stress testing | 100% area, 100% change, max bits |

```bash
./lcd_toggle_calc.py --preset 1080p60 --content video
```

## Display Presets

| Preset | Resolution | Pixel Clock | Refresh |
|--------|------------|-------------|---------|
| `wvga` | 800x480 | 33.3 MHz | 60 Hz |
| `xga` | 1024x768 | 65.0 MHz | 60 Hz |
| `wxga` | 1280x800 | 71.0 MHz | 60 Hz |
| `720p60` | 1280x720 | 74.25 MHz | 60 Hz |
| `1080p30` | 1920x1080 | 74.25 MHz | 30 Hz |
| `1080p60` | 1920x1080 | 148.5 MHz | 60 Hz |
| `4k30` | 3840x2160 | 297.0 MHz | 30 Hz |
| `4k60` | 3840x2160 | 594.0 MHz | 60 Hz |

Or specify custom parameters:

```bash
./lcd_toggle_calc.py --H 1024 --V 600 --fp 50.0 --fr 60 --W 18
```

## Pin Count Scaling

By default, calculations use the bus width (W) as the pin count. To model a larger GPIO bank or multiple interfaces, use `--pins`:

```bash
# Model 196 total GPIO pins
./lcd_toggle_calc.py --preset 1080p60 --content desktop --pins 196
```

This scales the "Total pins toggles/sec" output while keeping per-pin rates the same.

## Output Metrics

| Metric | Description |
|--------|-------------|
| H_avg | Weighted average bit flips per pixel per frame |
| rho | Blanking factor (pixel_clock / active_pixel_rate) |
| AF | Activity factor (fraction of bits toggling per pixel) |
| Toggles/sec (data bus) | Total toggles across data bus pins |
| Per-pin toggles/sec | Average toggles per GPIO pin |
| Total (N pins) | Aggregate toggles for specified pin count |
| Lifetime (Q) | Cumulative toggles in quadrillions over years |

## Theory

### Toggle Rate Calculation

The average bit flips per pixel per frame:
```
H_avg = Σ (alpha_i × c_i × h_i)
```

Where for each region i:
- `alpha_i` = fraction of screen area
- `c_i` = fraction of pixels changing per frame
- `h_i` = average Hamming distance per change

Total toggle rate:
```
toggles/sec = H × V × f_refresh × H_avg
```

### Why This Matters

**Reliability:** CMOS GPIO pins have finite toggle endurance, typically 10^12 to 10^15+ cycles depending on process technology. This tool helps you verify your application stays within safe margins over the product lifetime.

**Power:** Dynamic power consumption is proportional to toggle rate (P ∝ C × V² × f × α). Higher toggle rates mean more power dissipation.

**EMI:** Faster toggle rates produce more electromagnetic emissions. Understanding your toggle profile helps with EMC compliance.

## Sample Runs

### Automotive Dashboard (WVGA, mostly static)
```
$ ./lcd_toggle_calc.py --preset wvga --content static

--- Toggle Rates ---
Toggles/sec (data bus):   460.800 ktoggles/s
Per-pin toggles/sec:      19.200 ktoggles/s
Total (24 pins) toggles/sec: 460.800 ktoggles/s

Time to 1 quadrillion: 68.8147 years
```

### Media Player (1080p60, full video)
```
$ ./lcd_toggle_calc.py --preset 1080p60 --content video

--- Toggle Rates ---
Toggles/sec (data bus):   1.381 Gtoggles/s
Per-pin toggles/sec:      57.542 Mtoggles/s
Total (24 pins) toggles/sec: 1.381 Gtoggles/s

Time to 1 quadrillion: 0.0230 years
```

### Worst Case 4K (stress test)
```
$ ./lcd_toggle_calc.py --preset 4k60 --content worst

--- Toggle Rates ---
Toggles/sec (data bus):   11.944 Gtoggles/s
Per-pin toggles/sec:      497.664 Mtoggles/s
Total (24 pins) toggles/sec: 11.944 Gtoggles/s

Time to 1 quadrillion: 0.0027 years
```

## Command Reference

```
usage: lcd_toggle_calc.py [-h] [--preset PRESET] [--W W] [--fp FP] [--H H]
                          [--V V] [--fr FR] [--rho RHO] [--pins PINS]
                          [--content CONTENT] [--a1-3, --c1-3, --h1-3]
                          [-v] [--list-presets]

Display configuration:
  --preset    Use a display preset (720p60, 1080p60, etc.)
  --W         Bus width in bits (default: 24)
  --fp        Pixel clock in MHz (default: 148.5)
  --H         Horizontal resolution (default: 1920)
  --V         Vertical resolution (default: 1080)
  --fr        Refresh rate in Hz (default: 60)
  --rho       Override blanking factor (0 = auto)
  --pins      Total pins for aggregate calculation (default: W)

Content activity:
  --content   Use a content preset (static, desktop, video, worst)
  --aN        Region N area fraction (N = 1, 2, 3)
  --cN        Region N pixel change rate
  --hN        Region N bits per change

Output:
  -v          Verbose output with configuration details
  --list-presets  Show all available presets
```

## License

MIT License - see LICENSE file.

## Author

**Kyle Fox** - [kylefoxaustin](https://github.com/kylefoxaustin)

## Contributing

Issues and PRs welcome! Areas of interest:
- Additional display presets (MIPI DSI timing, LVDS, etc.)
- JSON/CSV output formats
- Integration with reliability modeling tools
- Additional content profile presets
