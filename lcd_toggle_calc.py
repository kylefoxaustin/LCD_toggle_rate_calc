#!/usr/bin/env python3
"""
LCD / GPIO Toggle Activity Calculator

Models the toggle rate of parallel LCD controller pins for various
display configurations and content activity assumptions.

Use cases:
- Estimating GPIO wear/lifetime for reliability analysis
- Power consumption estimation (dynamic power ∝ toggle rate)
- EMI analysis (higher toggle rates = more emissions)

Inputs:
- W: bus width (bits), typically 16, 18, or 24 for RGB interfaces
- f_p: pixel clock (MHz)
- H, V: resolution (active pixels)
- f_r: refresh rate (Hz)
- Regions: (alpha, c, h) triples defining content activity
    alpha: fraction of frame area (must sum to 1)
    c: fraction of pixels that change per frame in this region
    h: average Hamming distance (bit flips) per changed pixel (0..W)
- rho_override: manual blanking factor override (0 = auto-calculate)

Outputs:
- H_avg: weighted average bit flips per pixel per frame
- Activity factor AF
- Toggle rates (total bus and active-only)
- Per-pin toggle rates
- Lifetime projections (quadrillions of toggles)
- Time to reach 1 quadrillion toggles

Author: Kyle
License: MIT
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import sys

SECONDS_PER_YEAR = 60 * 60 * 24 * 365


# ============================================================================
# Common Display Presets
# ============================================================================
DISPLAY_PRESETS = {
    "720p60": {"H": 1280, "V": 720, "f_p_MHz": 74.25, "f_r": 60.0},
    "1080p60": {"H": 1920, "V": 1080, "f_p_MHz": 148.5, "f_r": 60.0},
    "1080p30": {"H": 1920, "V": 1080, "f_p_MHz": 74.25, "f_r": 30.0},
    "4k30": {"H": 3840, "V": 2160, "f_p_MHz": 297.0, "f_r": 30.0},
    "4k60": {"H": 3840, "V": 2160, "f_p_MHz": 594.0, "f_r": 60.0},
    "wvga": {"H": 800, "V": 480, "f_p_MHz": 33.3, "f_r": 60.0},
    "xga": {"H": 1024, "V": 768, "f_p_MHz": 65.0, "f_r": 60.0},
    "wxga": {"H": 1280, "V": 800, "f_p_MHz": 71.0, "f_r": 60.0},
}

# Content activity presets
CONTENT_PRESETS = {
    "static": [  # Static display (dashboard, HMI idle)
        {"alpha": 0.95, "c": 0.0, "h": 0},
        {"alpha": 0.05, "c": 0.10, "h": 4},
        {"alpha": 0.0, "c": 0.0, "h": 0},
    ],
    "desktop": [  # Typical desktop use (mixed static/dynamic)
        {"alpha": 0.30, "c": 0.0, "h": 0},
        {"alpha": 0.50, "c": 0.10, "h": 8},
        {"alpha": 0.20, "c": 1.0, "h": 12},
    ],
    "video": [  # Full-screen video playback
        {"alpha": 0.0, "c": 0.0, "h": 0},
        {"alpha": 0.10, "c": 0.5, "h": 6},
        {"alpha": 0.90, "c": 1.0, "h": 12},
    ],
    "worst": [  # Worst case (full screen, every pixel changes maximally)
        {"alpha": 0.0, "c": 0.0, "h": 0},
        {"alpha": 0.0, "c": 0.0, "h": 0},
        {"alpha": 1.0, "c": 1.0, "h": 24},  # Assumes W=24
    ],
}


@dataclass
class Region:
    """Defines a region of the display with specific activity characteristics."""
    alpha: float  # fraction of frame area (0..1)
    c: float      # fraction of pixels that change per frame (0..1)
    h: float      # average bit flips per changed pixel (0..W)

    def validate(self, bus_width: int) -> List[str]:
        """Return list of validation errors, empty if valid."""
        errors = []
        if not 0 <= self.alpha <= 1:
            errors.append(f"alpha={self.alpha} must be in [0, 1]")
        if not 0 <= self.c <= 1:
            errors.append(f"c={self.c} must be in [0, 1]")
        if not 0 <= self.h <= bus_width:
            errors.append(f"h={self.h} must be in [0, {bus_width}]")
        return errors


@dataclass
class Params:
    """Display and content parameters for toggle calculation."""
    W: int = 24                    # bus width (bits)
    f_p_MHz: float = 148.5         # pixel clock (MHz)
    H: int = 1920                  # horizontal resolution
    V: int = 1080                  # vertical resolution
    f_r: float = 60.0              # refresh rate (Hz)
    regions: List[Region] = None   # content activity regions
    rho_override: float = 0.0      # manual blanking factor (0 = auto)

    def __post_init__(self):
        if self.regions is None:
            # Default: typical desktop/mixed content
            self.regions = [
                Region(alpha=0.30, c=0.0, h=0),    # static regions
                Region(alpha=0.50, c=0.10, h=8),   # moderate activity
                Region(alpha=0.20, c=1.0, h=12),   # video/animation
            ]

    def validate(self) -> List[str]:
        """Return list of validation errors, empty if valid."""
        errors = []

        if self.W <= 0:
            errors.append(f"Bus width W={self.W} must be positive")
        if self.f_p_MHz <= 0:
            errors.append(f"Pixel clock f_p={self.f_p_MHz} MHz must be positive")
        if self.H <= 0:
            errors.append(f"H resolution={self.H} must be positive")
        if self.V <= 0:
            errors.append(f"V resolution={self.V} must be positive")
        if self.f_r <= 0:
            errors.append(f"Refresh rate={self.f_r} Hz must be positive")
        if self.rho_override < 0:
            errors.append(f"rho_override={self.rho_override} cannot be negative")

        # Validate regions
        if not self.regions:
            errors.append("At least one region must be defined")
        else:
            alpha_sum = sum(r.alpha for r in self.regions)
            if abs(alpha_sum - 1.0) > 0.001:
                errors.append(f"Region alphas sum to {alpha_sum}, should be 1.0")
            for i, r in enumerate(self.regions):
                for err in r.validate(self.W):
                    errors.append(f"Region {i+1}: {err}")

        # Sanity check: pixel clock should be >= active pixel rate
        active_rate = self.H * self.V * self.f_r
        pixel_clock_hz = self.f_p_MHz * 1_000_000
        if pixel_clock_hz < active_rate:
            errors.append(
                f"Pixel clock ({pixel_clock_hz:.0f} Hz) < active rate "
                f"({active_rate:.0f} px/s) - impossible configuration"
            )

        return errors


class ActivityTool:
    """Calculator for LCD bus toggle activity and lifetime estimates."""

    def __init__(self, p: Params):
        self.p = p

    def compute(self) -> Dict:
        """
        Compute toggle activity metrics.

        Returns dict with:
            H_avg: weighted average bit flips per pixel per frame
            active_rate: active pixels per second (H * V * f_r)
            pixel_clock_hz: pixel clock in Hz
            rho: blanking factor (pixel_clock / active_rate)
            AF: activity factor (fraction of max possible toggles)
            toggles_bus: total bus toggles per second
            toggles_active: toggles during active pixels only
            per_pin: average toggles per pin per second
        """
        # Weighted average Hamming distance per pixel per frame
        H_avg = sum(r.alpha * r.c * r.h for r in self.p.regions)

        # Active pixel rate
        active_rate = self.p.H * self.p.V * self.p.f_r

        # Pixel clock
        pixel_clock_hz = self.p.f_p_MHz * 1_000_000.0

        # Blanking factor: ratio of total pixel clocks to active pixels
        # This accounts for horizontal and vertical blanking periods
        if self.p.rho_override > 0:
            rho = self.p.rho_override
        else:
            rho = pixel_clock_hz / active_rate

        # Activity factor: normalized toggle rate
        # (H_avg / W) gives fraction of bits toggling per pixel
        # Multiplied by rho to account for blanking overhead
        AF = (H_avg / self.p.W) * rho

        # Total bus toggles per second
        # This represents toggles across all W pins
        toggles_bus = pixel_clock_hz * self.p.W * AF

        # Toggles during active pixels only (no blanking)
        toggles_active = active_rate * H_avg

        # Per-pin average toggle rate
        per_pin = toggles_bus / self.p.W

        return {
            "H_avg": H_avg,
            "active_rate": active_rate,
            "pixel_clock_hz": pixel_clock_hz,
            "rho": rho,
            "AF": AF,
            "toggles_bus": toggles_bus,
            "toggles_active": toggles_active,
            "per_pin": per_pin,
        }

    @staticmethod
    def lifetime_quadrillions(
        toggles_per_sec: float,
        years_list: Tuple[int, ...] = (1, 5, 10, 25, 50, 75, 100)
    ) -> Dict[int, float]:
        """Calculate total toggles (in quadrillions) for given year counts."""
        return {
            y: (toggles_per_sec * SECONDS_PER_YEAR * y) / 1e15
            for y in years_list
        }

    @staticmethod
    def years_to_one_quadrillion(toggles_per_sec: float) -> float:
        """Calculate years to reach 1 quadrillion (1e15) toggles."""
        if toggles_per_sec <= 0:
            return float("inf")
        return (1e15 / toggles_per_sec) / SECONDS_PER_YEAR


def format_engineering(value: float, unit: str = "") -> str:
    """Format number in engineering notation with SI prefix."""
    if value == 0:
        return f"0 {unit}".strip()

    prefixes = [
        (1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"),
        (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"),
    ]
    for threshold, prefix in prefixes:
        if abs(value) >= threshold:
            return f"{value/threshold:.3f} {prefix}{unit}".strip()
    return f"{value:.3e} {unit}".strip()


def print_results(p: Params, res: Dict, verbose: bool = False):
    """Print formatted results."""
    print("\n" + "=" * 60)
    print("LCD/GPIO Toggle Activity Analysis")
    print("=" * 60)

    if verbose:
        print("\n--- Configuration ---")
        print(f"Bus width:      {p.W} bits")
        print(f"Resolution:     {p.H} x {p.V}")
        print(f"Pixel clock:    {p.f_p_MHz} MHz")
        print(f"Refresh rate:   {p.f_r} Hz")
        print(f"\nContent regions:")
        for i, r in enumerate(p.regions, 1):
            if r.alpha > 0:
                print(f"  Region {i}: {r.alpha*100:.0f}% area, "
                      f"{r.c*100:.0f}% pixels change, "
                      f"{r.h:.1f} bits/change")

    print("\n--- Activity Metrics ---")
    print(f"H_avg (bit flips/pixel/frame):  {res['H_avg']:.4f}")
    print(f"Blanking factor (rho):          {res['rho']:.4f}")
    print(f"Activity factor (AF):           {res['AF']:.6f}")

    print("\n--- Toggle Rates ---")
    print(f"Bus toggles/sec:     {format_engineering(res['toggles_bus'], 'toggles/s')}")
    print(f"Active-only/sec:     {format_engineering(res['toggles_active'], 'toggles/s')}")
    print(f"Per-pin toggles/sec: {format_engineering(res['per_pin'], 'toggles/s')}")

    print("\n--- Lifetime Projections (quadrillions of toggles) ---")
    life = ActivityTool.lifetime_quadrillions(res["toggles_bus"])
    for y, q in life.items():
        print(f"  {y:>3} years: {q:>12,.2f} Q")

    years_to_1q = ActivityTool.years_to_one_quadrillion(res["toggles_bus"])
    print(f"\nTime to 1 quadrillion: {years_to_1q:.4f} years")

    # Helpful context
    if verbose:
        print("\n--- Context ---")
        print("Typical CMOS GPIO toggle endurance: 1e12 - 1e15+ cycles")
        print("(Consult your silicon vendor's reliability data)")


def main():
    import argparse

    ap = argparse.ArgumentParser(
        description="LCD/GPIO Toggle Activity Calculator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --preset 1080p60 --content desktop
  %(prog)s --H 800 --V 480 --fp 33.3 --fr 60
  %(prog)s --preset 4k60 --content video -v

Display presets: """ + ", ".join(DISPLAY_PRESETS.keys()) + """
Content presets: """ + ", ".join(CONTENT_PRESETS.keys())
    )

    # Display configuration
    disp = ap.add_argument_group("Display configuration")
    disp.add_argument("--preset", choices=DISPLAY_PRESETS.keys(),
                      help="Use a display preset")
    disp.add_argument("--W", type=int, default=24,
                      help="Bus width in bits (default: 24)")
    disp.add_argument("--fp", type=float, default=148.5,
                      help="Pixel clock in MHz (default: 148.5)")
    disp.add_argument("--H", type=int, default=1920,
                      help="Horizontal resolution (default: 1920)")
    disp.add_argument("--V", type=int, default=1080,
                      help="Vertical resolution (default: 1080)")
    disp.add_argument("--fr", type=float, default=60.0,
                      help="Refresh rate in Hz (default: 60)")
    disp.add_argument("--rho", type=float, default=0.0,
                      help="Override blanking factor (0 = auto)")

    # Content activity
    content = ap.add_argument_group("Content activity")
    content.add_argument("--content", choices=CONTENT_PRESETS.keys(),
                         help="Use a content activity preset")
    content.add_argument("--a1", type=float, default=0.30,
                         help="Region 1 area fraction")
    content.add_argument("--c1", type=float, default=0.0,
                         help="Region 1 change rate")
    content.add_argument("--h1", type=float, default=0,
                         help="Region 1 bits per change")
    content.add_argument("--a2", type=float, default=0.50)
    content.add_argument("--c2", type=float, default=0.10)
    content.add_argument("--h2", type=float, default=8)
    content.add_argument("--a3", type=float, default=0.20)
    content.add_argument("--c3", type=float, default=1.0)
    content.add_argument("--h3", type=float, default=12)

    # Output options
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Show detailed configuration and context")
    ap.add_argument("--list-presets", action="store_true",
                    help="List all available presets and exit")

    args = ap.parse_args()

    # Handle --list-presets
    if args.list_presets:
        print("\nDisplay Presets:")
        print("-" * 50)
        for name, cfg in DISPLAY_PRESETS.items():
            print(f"  {name:12s}: {cfg['H']}x{cfg['V']} @ {cfg['f_r']}Hz, "
                  f"{cfg['f_p_MHz']} MHz pixel clock")
        print("\nContent Presets:")
        print("-" * 50)
        for name, regions in CONTENT_PRESETS.items():
            active_regions = [r for r in regions if r["alpha"] > 0]
            desc = ", ".join(
                f"{r['alpha']*100:.0f}%@c={r['c']:.1f}"
                for r in active_regions
            )
            print(f"  {name:12s}: {desc}")
        return

    # Build display parameters
    if args.preset:
        preset = DISPLAY_PRESETS[args.preset]
        H = preset["H"]
        V = preset["V"]
        f_p_MHz = preset["f_p_MHz"]
        f_r = preset["f_r"]
    else:
        H = args.H
        V = args.V
        f_p_MHz = args.fp
        f_r = args.fr

    # Build content regions
    if args.content:
        regions = [
            Region(**r) for r in CONTENT_PRESETS[args.content]
        ]
        # Adjust worst-case h value for actual bus width
        if args.content == "worst":
            regions[2].h = args.W
    else:
        regions = [
            Region(args.a1, args.c1, args.h1),
            Region(args.a2, args.c2, args.h2),
            Region(args.a3, args.c3, args.h3),
        ]

    # Normalize alphas if they don't sum to 1
    alpha_sum = sum(r.alpha for r in regions)
    if alpha_sum <= 0:
        print("Error: region alphas must sum to > 0", file=sys.stderr)
        sys.exit(1)
    if abs(alpha_sum - 1.0) > 0.001:
        print(f"Note: normalizing region alphas (sum was {alpha_sum:.3f})",
              file=sys.stderr)
        regions = [Region(r.alpha / alpha_sum, r.c, r.h) for r in regions]

    # Create parameters and validate
    p = Params(
        W=args.W,
        f_p_MHz=f_p_MHz,
        H=H,
        V=V,
        f_r=f_r,
        regions=regions,
        rho_override=args.rho,
    )

    errors = p.validate()
    if errors:
        print("Configuration errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Compute and display
    tool = ActivityTool(p)
    res = tool.compute()
    print_results(p, res, verbose=args.verbose)


if __name__ == "__main__":
    main()
