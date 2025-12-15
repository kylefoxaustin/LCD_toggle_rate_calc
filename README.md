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
git clone https://github.com/yourusername/lcd-toggle-calc.git
cd lcd-toggle-calc
chmod +x lcd_toggle_calc.py
```

No external dependencies - uses Python 3.7+ standard library only.

## Usage

### Basic usage with defaults (1080p60, desktop content):
```bash
./lcd_toggle_calc.py
```

### Using presets:
```bash
./lcd_toggle_calc.py --preset 1080p60 --content desktop
./lcd_toggle_calc.py --preset 4k60 --content video -v
./lcd_toggle_calc.py --preset wvga --content static
```

### Custom configuration:
```bash
./lcd_toggle_calc.py --H 800 --V 480 --fp 33.3 --fr 60 --W 24
```

### List available presets:
```bash
./lcd_toggle_calc.py --list-presets
```

## Content Activity Model

The tool models screen content using up to 3 regions, each with:
- **alpha**: Fraction of screen area (must sum to 1.0)
- **c**: Fraction of pixels in that region that change each frame
- **h**: Average Hamming distance (bit flips) per changed pixel

### Built-in Content Presets

| Preset | Description | Typical Use Case |
|--------|-------------|------------------|
| `static` | 95% unchanging, 5% minor updates | HMI idle, dashboards |
| `desktop` | Mixed static/dynamic areas | General desktop use |
| `video` | 90% full-motion video | Media playback |
| `worst` | 100% area, 100% change, max bits | Stress testing |

### Custom regions:
```bash
./lcd_toggle_calc.py --a1 0.8 --c1 0.0 --h1 0 \
                     --a2 0.2 --c2 0.5 --h2 12 \
                     --a3 0.0 --c3 0.0 --h3 0
```

## Output Metrics

| Metric | Description |
|--------|-------------|
| H_avg | Weighted average bit flips per pixel per frame |
| rho | Blanking factor (pixel_clock / active_pixel_rate) |
| AF | Activity factor (normalized toggle rate) |
| Bus toggles/sec | Total toggles across all pins |
| Per-pin toggles/sec | Average toggles per GPIO pin |
| Lifetime (Q) | Cumulative toggles in quadrillions |

## Display Presets

| Preset | Resolution | Pixel Clock | Refresh |
|--------|------------|-------------|---------|
| wvga | 800x480 | 33.3 MHz | 60 Hz |
| xga | 1024x768 | 65.0 MHz | 60 Hz |
| wxga | 1280x800 | 71.0 MHz | 60 Hz |
| 720p60 | 1280x720 | 74.25 MHz | 60 Hz |
| 1080p30 | 1920x1080 | 74.25 MHz | 30 Hz |
| 1080p60 | 1920x1080 | 148.5 MHz | 60 Hz |
| 4k30 | 3840x2160 | 297.0 MHz | 30 Hz |
| 4k60 | 3840x2160 | 594.0 MHz | 60 Hz |

## Theory

### Toggle Rate Calculation

The average bit flips per pixel per frame:
```
H_avg = Σ (alpha_i × c_i × h_i)
```

The blanking factor accounts for H-blank and V-blank periods:
```
rho = f_pixel / (H × V × f_refresh)
```

Activity factor (fraction of theoretical maximum):
```
AF = (H_avg / W) × rho
```

Total bus toggle rate:
```
toggles/sec = f_pixel × W × AF
```

### Reliability Context

Typical CMOS GPIO endurance ranges from 10^12 to 10^15+ toggle cycles. Consult your silicon vendor's reliability data for specific limits. This tool helps you estimate whether your application falls within safe margins.

## Examples

### Automotive dashboard (mostly static):
```bash
$ ./lcd_toggle_calc.py --preset wxga --content static -v

--- Activity Metrics ---
H_avg (bit flips/pixel/frame):  0.0200
Blanking factor (rho):          1.1556
Activity factor (AF):           0.000963

--- Toggle Rates ---
Bus toggles/sec:     1.641 Mtoggle/s
Per-pin toggles/sec: 68.366 ktoggle/s

--- Lifetime Projections (quadrillions of toggles) ---
   10 years:         0.52 Q
   25 years:         1.29 Q
```

### Video playback stress test:
```bash
$ ./lcd_toggle_calc.py --preset 1080p60 --content video

--- Toggle Rates ---
Bus toggles/sec:     45.619 Gtoggle/s
Per-pin toggles/sec: 1.901 Gtoggle/s
```

## License

MIT License - see LICENSE file.

## Contributing

Issues and PRs welcome! Areas of interest:
- Additional display presets (MIPI DSI timing, LVDS, etc.)
- JSON/CSV output formats
- Integration with reliability modeling tools
