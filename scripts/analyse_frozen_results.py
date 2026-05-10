#!/usr/bin/env python3
"""Analyse the frozen 2026-05-10 PlutoSDR bring-up CSVs."""
import csv
from pathlib import Path
from statistics import mean, median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path("results")
PLOTS = Path("docs/plots")
SUMMARY = Path("docs/frozen_results_analysis_2026-05-10.md")


def read_csv(name):
    with (RESULTS / name).open() as f:
        return list(csv.DictReader(f))


def vals(rows, key):
    return [float(r[key]) for r in rows if r.get(key) not in (None, "")]


def stats(rows, key):
    x = vals(rows, key)
    if not x:
        return None
    return {"n": len(x), "min": min(x), "mean": mean(x), "median": median(x), "max": max(x)}


def fmt(s, pct=False, unit=""):
    if s is None:
        return "n/a"
    scale = 100 if pct else 1
    return f"min {s['min']*scale:.2f}{unit}, mean {s['mean']*scale:.2f}{unit}, median {s['median']*scale:.2f}{unit}, max {s['max']*scale:.2f}{unit}"


def plot_retune(rx, tx):
    PLOTS.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(vals(rx, "i"), vals(rx, "retune_ms"), marker="o", label="RX retune")
    ax.plot(vals(tx, "i"), vals(tx, "retune_ms"), marker="o", label="TX retune")
    ax.set_title("PlutoSDR host-controlled retune timing")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Retune time (ms)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    out = PLOTS / "retune_timing.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_ser():
    datasets = {
        "link -60 dB": read_csv("link_smoke_915mhz.csv"),
        "link -50 dB": read_csv("link_smoke_915mhz_txm50.csv"),
        "FH -60 dB": read_csv("fh_loop_914_916mhz.csv"),
        "FH -50 dB": read_csv("fh_loop_914_916mhz_txm50.csv"),
        "UCB live -50 dB": read_csv("live_mab_ucb_914_916mhz_txm50.csv"),
    }
    labels = list(datasets)
    data = [[100 * x for x in vals(rows, "ser")] for rows in datasets.values()]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.boxplot(data, labels=labels, showmeans=True)
    ax.set_title("Frozen PlutoSDR runs: symbol error rate distribution")
    ax.set_ylabel("SER (%)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(axis="x", rotation=20)
    out = PLOTS / "ser_distribution.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_live_ucb(live):
    hops = vals(live, "hop")
    ser = [100 * x for x in vals(live, "ser")]
    reward = vals(live, "reward")
    margin = vals(live, "peak_margin")
    arms = vals(live, "arm")
    fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
    axes[0].plot(hops, ser, marker="o")
    axes[0].set_ylabel("SER (%)")
    axes[0].set_title("Live UCB hardware loop")
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(hops, reward, marker="o", color="tab:green")
    axes[1].set_ylabel("Reward (1 - SER)")
    axes[1].grid(True, alpha=0.3)
    axes[2].step(hops, arms, where="mid", label="selected arm")
    axes[2].plot(hops, margin, marker=".", color="tab:orange", label="peak margin")
    axes[2].set_ylabel("Arm / margin")
    axes[2].set_xlabel("Hop")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend()
    out = PLOTS / "live_ucb_loop.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_mab_sim(sim):
    by_agent = {}
    for r in sim:
        by_agent.setdefault(r["agent"], []).append(r)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for agent, rows in by_agent.items():
        ax.plot(vals(rows, "t"), vals(rows, "cumulative_regret"), label=agent)
    ax.set_title("Toy MAB simulation: cumulative regret")
    ax.set_xlabel("Step")
    ax.set_ylabel("Cumulative regret")
    ax.grid(True, alpha=0.3)
    ax.legend()
    out = PLOTS / "mab_sim_regret.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def main():
    rx = read_csv("rx_retune_benchmark.csv")
    tx = read_csv("tx_retune_benchmark.csv")
    link60 = read_csv("link_smoke_915mhz.csv")
    link50 = read_csv("link_smoke_915mhz_txm50.csv")
    fh60 = read_csv("fh_loop_914_916mhz.csv")
    fh50 = read_csv("fh_loop_914_916mhz_txm50.csv")
    live = read_csv("live_mab_ucb_914_916mhz_txm50.csv")
    sim = read_csv("mab_sim.csv")

    plots = [plot_retune(rx, tx), plot_ser(), plot_live_ucb(live), plot_mab_sim(sim)]

    live_clean = [r for r in live if int(float(r["peaks"])) <= 40]
    link50_clean = [r for r in link50 if int(float(r["peaks"])) <= 40]
    fh50_clean = [r for r in fh50 if int(float(r["peaks"])) <= 40]

    md = []
    md.append("# Frozen PlutoSDR Results Analysis — 2026-05-10\n")
    md.append("This analysis uses only the frozen CSV files from the 2026-05-10 PlutoSDR bring-up checkpoint. No additional SDR experiments were run.\n")
    md.append("## Generated plots\n")
    for p in plots:
        md.append(f"- `{p}`")
    md.append("\n## Key quantitative summaries\n")
    md.append(f"- RX retune: {fmt(stats(rx, 'retune_ms'), unit=' ms')}")
    md.append(f"- TX retune: {fmt(stats(tx, 'retune_ms'), unit=' ms')}")
    md.append(f"- RX retune + capture: {fmt(stats(rx, 'retune_capture_ms'), unit=' ms')}")
    md.append(f"- Fixed 915 MHz link, -60 dB TX: SER {fmt(stats(link60, 'ser'), pct=True, unit='%')}")
    md.append(f"- Fixed 915 MHz link, -50 dB TX: SER {fmt(stats(link50, 'ser'), pct=True, unit='%')}")
    md.append(f"- Fixed 915 MHz link, -50 dB TX, no abnormal peak-count outlier: SER {fmt(stats(link50_clean, 'ser'), pct=True, unit='%')}")
    md.append(f"- FH loop 914/915/916 MHz, -50 dB TX: SER {fmt(stats(fh50, 'ser'), pct=True, unit='%')}")
    md.append(f"- FH loop 914/915/916 MHz, -50 dB TX, normal peak count: SER {fmt(stats(fh50_clean, 'ser'), pct=True, unit='%')}")
    md.append(f"- FH loop 914/915/916 MHz, -50 dB TX: sequential TX+RX retune {fmt(stats(fh50, 'retune_ms'), unit=' ms')}")
    md.append(f"- Live UCB hardware loop: SER {fmt(stats(live, 'ser'), pct=True, unit='%')}")
    md.append(f"- Live UCB hardware loop, normal peak count: SER {fmt(stats(live_clean, 'ser'), pct=True, unit='%')}")
    md.append(f"- Live UCB hardware loop: reward {fmt(stats(live, 'reward'))}")
    md.append(f"- Live UCB hardware loop: peak margin {fmt(stats(live, 'peak_margin'), unit='×')}")

    md.append("\n## Interpretation\n")
    md.append("1. **The basic PlutoSDR OFDM/QPSK link is working.** The clean fixed-link -50 dB run stayed between 0% and 6.51% SER over 10 bursts, substantially better than the -60 dB run, which had a 76.28% acquisition/timing outlier.")
    md.append("2. **Frequency hopping works at the bring-up level.** The -50 dB three-channel hop loop achieved 1.84% mean SER over 12 hops with no severe outlier, while sequential TX+RX retuning averaged about 7.98 ms.")
    md.append("3. **The first hardware-in-the-loop MAB path is functional.** UCB selected channels, retuned both radios, demodulated bursts, converted SER to reward, and updated online. The 18-hop run had 6.41% mean SER including one clear timing/acquisition outlier; excluding abnormal peak-count cases gives a representative SER near the low-single-digit range.")
    md.append("4. **Acquisition confidence needs to become part of the reward gate.** Outliers correlate with abnormal preamble peak counts (e.g. 64 peaks), so packet validity should be separated from channel quality before comparing algorithms.")
    md.append("5. **The ≤2 ms retune claim is not supported by the measured host-control path.** Single-radio retunes were about 3.9 ms mean; sequential TX+RX retunes were about 8 ms mean. This should be framed as a measured timing budget, not a failure of the thesis.")

    md.append("\n## Claim coverage impact\n")
    md.append("- **C5 (OFDM/QPSK suitability): strengthened but not complete.** Frozen data supports feasibility of OFDM/QPSK at 915 MHz; controlled BLER/PER and interference tests are still needed.")
    md.append("- **C7 (PlutoSDR can support useful MAB-FH): strengthened.** Both fixed-link and hopping runs worked on two Plutos. Useful hop rate must be bounded by measured retune/capture/acquisition timing.")
    md.append("- **C10 (MAB-FH beats static/random): not yet covered by hardware.** Only UCB was run live. Need side-by-side frozen-protocol trials with static/random/UCB/TS/EXP3 and a controlled interferer.")
    md.append("- **C13/C14/C15 (BLER/throughput targets): still uncovered.** Current SER proxy is useful for bring-up but is not packet BLER or throughput.")
    md.append("- **C18/C27/C30 (preamble/acquisition pipeline): strengthened.** ZC/OFDM acquisition works often enough for bring-up, but abnormal peak counts show packet-validity gating is necessary.")
    md.append("- **C19 (≤2 ms retune): contradicted for current implementation.** This should remain BLOCKED unless the architecture changes or lower-level tuning proves faster.")
    md.append("- **C21 (MAB computation negligible): partly implied but not directly measured.** Demod/capture/retune dominate logs; add explicit agent decision timing later.")

    md.append("\n## Recommended progress-update wording\n")
    md.append("> A first PlutoSDR hardware bring-up was completed using two networked ADALM-Pluto units. The OFDM/QPSK link was validated at 915 MHz, followed by a three-channel frequency-hopping loop over 914/915/916 MHz. At -50 dB TX attenuation the fixed-link run achieved 2.54% mean SER, while the three-channel hop loop achieved 1.84% mean SER over 12 hops. A first live UCB multi-armed-bandit control loop was also demonstrated, using measured SER as a bounded reward (`1 - SER`). The main risk identified is timing/acquisition robustness: host-controlled retuning averaged about 3.9 ms per radio and about 8 ms for sequential TX+RX retunes, contradicting the earlier ≤2 ms assumption and motivating packet-validity gating before algorithm comparison.\n")

    SUMMARY.write_text("\n".join(md) + "\n")
    print(SUMMARY)
    for p in plots:
        print(p)


if __name__ == "__main__":
    main()
