export function ScanStyles() {
  return (
    <style>{`
      .scan-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
      .scan-card {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 18px;
        background: linear-gradient(160deg, rgba(18,22,30,0.95), rgba(8,10,14,0.98));
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
        position: relative;
        overflow: hidden;
      }
      .scan-card.running::before {
        content: '';
        position: absolute;
        inset: 0 auto 0 0;
        width: 3px;
        background: linear-gradient(180deg, #38bdf8, #6366f1);
        animation: scan-pulse 1.4s ease-in-out infinite;
      }
      @keyframes scan-pulse { 0%,100% { opacity: 0.45; } 50% { opacity: 1; } }
      .scan-card-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
      .scan-card-title { display: flex; align-items: center; gap: 10px; font-weight: 700; color: #fff; }
      .scan-card-title i { font-size: 20px; }
      .scan-badge {
        display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px;
        font-size: 10px; font-weight: 700; letter-spacing: 0.4px; text-transform: uppercase;
        border: 1px solid rgba(255,255,255,0.12);
      }
      .scan-badge.ok { color: #34d399; border-color: rgba(52,211,153,0.35); background: rgba(52,211,153,0.08); }
      .scan-badge.run { color: #67e8f9; border-color: rgba(103,232,249,0.35); background: rgba(103,232,249,0.08); }
      .scan-badge.err { color: #fb7185; border-color: rgba(251,113,133,0.35); background: rgba(251,113,133,0.08); }
      .scan-badge.warn { color: #fbbf24; border-color: rgba(251,191,36,0.35); background: rgba(251,191,36,0.08); }
      .scan-badge.idle { color: #94a3b8; border-color: rgba(148,163,184,0.25); background: rgba(148,163,184,0.06); }
      .scan-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
      .scan-metric span { display: block; font-size: 11px; color: #94a3b8; }
      .scan-metric strong { font-size: 14px; color: #e2e8f0; font-family: var(--font-mono, monospace); }
      .scan-message { margin-top: 12px; font-size: 12px; color: #a3aab8; line-height: 1.5; }
      .scan-meta { margin-top: 10px; font-size: 11px; color: #64748b; display: flex; flex-wrap: wrap; gap: 10px; }
      .scan-progress { margin-top: 12px; height: 6px; border-radius: 999px; background: rgba(255,255,255,0.06); overflow: hidden; }
      .scan-progress > div { height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); transition: width 0.4s ease; }
      .scan-panel {
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 20px;
        background: rgba(12, 16, 24, 0.75);
        margin-bottom: 20px;
      }
      .scan-panel-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
      .scan-panel-title { font-size: 16px; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }
      .scan-actions { display: flex; gap: 8px; flex-wrap: wrap; }
      .scan-spinner { animation: scan-spin 1s linear infinite; display: inline-block; }
      @keyframes scan-spin { 100% { transform: rotate(360deg); } }
    `}</style>
  );
}
