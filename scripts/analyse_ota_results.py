#!/usr/bin/env python3
"""Analyse close-range antenna OTA results vs frozen coax baseline."""
import csv
from pathlib import Path
from statistics import mean, median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path("results")
PLOTS = Path("docs/plots")
OUT = Path("docs/ota_close_results_analysis_2026-05-10.md")


def read(name):
    with (RESULTS / name).open() as f:
        return list(csv.DictReader(f))


def vals(rows, key):
    out=[]
    for r in rows:
        try: out.append(float(r[key]))
        except Exception: pass
    return out


def stat(rows, key):
    x=vals(rows,key)
    return (min(x), mean(x), median(x), max(x)) if x else None


def fmt(s, pct=False, unit=""):
    scale=100 if pct else 1
    return f"min {s[0]*scale:.2f}{unit}, mean {s[1]*scale:.2f}{unit}, median {s[2]*scale:.2f}{unit}, max {s[3]*scale:.2f}{unit}"


def boxplot_ser(datasets):
    labels=list(datasets)
    data=[[100*x for x in vals(rows,'ser')] for rows in datasets.values()]
    fig, ax=plt.subplots(figsize=(9.5,4.8))
    ax.boxplot(data, tick_labels=labels, showmeans=True)
    ax.set_title('Coax baseline vs close-range antenna OTA: SER')
    ax.set_ylabel('SER (%)')
    ax.grid(True, axis='y', alpha=0.3)
    ax.tick_params(axis='x', rotation=18)
    PLOTS.mkdir(parents=True, exist_ok=True)
    out=PLOTS/'coax_vs_ota_ser.png'
    fig.tight_layout(); fig.savefig(out,dpi=180); plt.close(fig)
    return out


def peaks_plot(datasets):
    labels=list(datasets)
    means=[mean(vals(rows,'peaks')) for rows in datasets.values()]
    fig, ax=plt.subplots(figsize=(8.5,4.5))
    ax.bar(labels, means)
    ax.axhline(32, color='tab:green', linestyle='--', linewidth=1, label='Expected repeated preamble count region (coax observed ~32)')
    ax.set_title('Mean detected ZC preamble peaks')
    ax.set_ylabel('Mean peak count')
    ax.grid(True, axis='y', alpha=0.3)
    ax.tick_params(axis='x', rotation=18)
    ax.legend(fontsize=8)
    out=PLOTS/'coax_vs_ota_preamble_peaks.png'
    fig.tight_layout(); fig.savefig(out,dpi=180); plt.close(fig)
    return out


def live_plot(rows):
    hops=vals(rows,'hop')
    ser=[100*x for x in vals(rows,'ser')]
    margin=vals(rows,'peak_margin')
    reward=vals(rows,'reward')
    fig, axes=plt.subplots(3,1,figsize=(9,8),sharex=True)
    axes[0].plot(hops,ser,marker='o'); axes[0].set_ylabel('SER (%)'); axes[0].set_title('Close-range antenna OTA live UCB loop (-40 dB)'); axes[0].grid(True,alpha=.3)
    axes[1].plot(hops,reward,marker='o',color='tab:green'); axes[1].set_ylabel('Reward'); axes[1].grid(True,alpha=.3)
    axes[2].plot(hops,margin,marker='o',color='tab:orange'); axes[2].axhline(1.0,color='tab:red',linestyle='--',linewidth=1,label='threshold crossing boundary'); axes[2].set_ylabel('Peak margin'); axes[2].set_xlabel('Hop'); axes[2].grid(True,alpha=.3); axes[2].legend()
    out=PLOTS/'ota_live_ucb_loop.png'
    fig.tight_layout(); fig.savefig(out,dpi=180); plt.close(fig)
    return out


def main():
    data={
      'Coax link -50': read('link_smoke_915mhz_txm50.csv'),
      'OTA link -60': read('link_smoke_ota_close_915mhz_txm60.csv'),
      'OTA link -50': read('link_smoke_ota_close_915mhz_txm50.csv'),
      'OTA link -40': read('link_smoke_ota_close_915mhz_txm40.csv'),
      'Coax FH -50': read('fh_loop_914_916mhz_txm50.csv'),
      'OTA FH -40': read('fh_loop_ota_close_914_916mhz_txm40.csv'),
      'OTA UCB -40': read('live_mab_ucb_ota_close_914_916mhz_txm40.csv'),
    }
    plots=[boxplot_ser(data), peaks_plot({k:v for k,v in data.items() if 'link' in k or 'FH' in k}), live_plot(data['OTA UCB -40'])]
    md=['# Close-Range Antenna OTA Results Analysis — 2026-05-10','',
        'This analysis uses the new close-range antenna dataset collected after replacing the coax connection with two nearby antennas. The coax dataset remains the controlled bench baseline; the OTA dataset tests the same code path with a real radiated link.','',
        '## Plots','']
    md += [f'- `{p}`' for p in plots]
    md += ['', '## Summary statistics','']
    for name, rows in data.items():
        md.append(f'- {name}: SER {fmt(stat(rows,"ser"), pct=True, unit="%")}; peaks {fmt(stat(rows,"peaks"))}')
    live=data['OTA UCB -40']
    md += ['', '## Interpretation','',
      '1. The close-range antenna link did not acquire reliably at -60, -50, or -40 dB TX attenuation. SER stayed around 70–80%, close to an effectively failed QPSK demodulation, and detected preamble peaks were near 0–3 rather than the ~32 peak pattern seen in the coax runs.',
      '2. Increasing TX level from -60 to -40 dB did not materially improve acquisition. That suggests the current problem may not be simple link margin alone; antenna mismatch/orientation, RX gain, saturation, cabling removal changing amplitude assumptions, thresholding, or frame timing logic may be involved.',
      '3. The live UCB loop still executed as a control loop, but its rewards were not meaningful channel-quality rewards. Mean reward was about 0.25 because SER was high on all channels. In this condition the agent cannot learn useful frequency preference; it is mostly observing receiver failure.',
      '4. This is useful thesis evidence because it separates two milestones: coax validated the digital SDR/control path, while OTA now exposes the next real RF/acquisition problem that must be solved before anti-jamming experiments are credible.',
      '', '## Claim impact','',
      '- C5 / OFDM-QPSK suitability: coax evidence remains positive, but OTA evidence weakens any broad claim that the current receiver is already robust. Keep this as partially-supported only.',
      '- C7 / PlutoSDR MAB-FH feasibility: control-path feasibility remains supported, but OTA link feasibility is not yet demonstrated with the current antenna setup.',
      '- C18/C27/C30 / acquisition pipeline: the OTA dataset challenges the current ZC threshold/acquisition implementation. Packet-validity gating and acquisition debugging are now immediate blockers.',
      '- C10 / MAB beats baselines: still not tested. OTA data is not suitable for algorithm comparison because all channels are failing similarly.',
      '- C19 / retune timing: unchanged; retune timing remains around 8 ms sequential TX+RX.',
    ]
    OUT.write_text('\n'.join(md)+'\n')
    print(OUT)
    for p in plots: print(p)

if __name__=='__main__': main()
