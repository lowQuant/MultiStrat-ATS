import React, { useEffect, useRef, useState } from 'react';

interface HistoryData {
  symbol: string;
  dates: string[];
  open: (number | null)[];
  high: (number | null)[];
  low: (number | null)[];
  close: (number | null)[];
}

interface MiniOHLCChartProps {
  symbol: string;
  width?: number;
  height?: number;
}

const MiniOHLCChart: React.FC<MiniOHLCChartProps> = ({ symbol, width = 720, height = 280 }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [data, setData] = useState<HistoryData | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError('');
        const res = await fetch(`http://127.0.0.1:8000/api/scanner/history?symbol=${encodeURIComponent(symbol)}`);
        const json = await res.json();
        if (json.success) {
          setData(json.data as HistoryData);
        } else {
          setError(json.error || 'Failed to load history');
        }
      } catch (e: any) {
        setError(String(e?.message || e));
      } finally {
        setLoading(false);
      }
    };
    if (symbol) fetchData();
  }, [symbol]);

  useEffect(() => {
    if (!data || !canvasRef.current) return;
    const ctx = canvasRef.current.getContext('2d');
    if (!ctx) return;

    // Prepare close series
    const closes = (data.close || []).filter((v): v is number => v !== null && !Number.isNaN(v));
    if (closes.length === 0) return;

    const pad = { left: 40, right: 10, top: 10, bottom: 20 };
    const W = canvasRef.current.width;
    const H = canvasRef.current.height;
    const plotW = W - pad.left - pad.right;
    const plotH = H - pad.top - pad.bottom;

    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const n = closes.length;

    const xFor = (i: number) => pad.left + (i / (n - 1)) * plotW;
    const yFor = (v: number) => pad.top + (1 - (v - min) / Math.max(1e-9, max - min)) * plotH;

    // Clear
    ctx.clearRect(0, 0, W, H);

    // Background
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--background') || '#ffffff';
    ctx.fillRect(0, 0, W, H);

    // Grid (simple)
    ctx.strokeStyle = 'rgba(0,0,0,0.08)';
    ctx.lineWidth = 1;
    for (let g = 0; g <= 4; g++) {
      const y = pad.top + (g / 4) * plotH;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(W - pad.right, y);
      ctx.stroke();
    }

    // Axis labels (min/max)
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(max.toFixed(2), pad.left - 6, yFor(max) + 4);
    ctx.fillText(min.toFixed(2), pad.left - 6, yFor(min) + 4);

    // Price line
    ctx.strokeStyle = '#0ea5e9'; // sky-500
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    closes.forEach((v, i) => {
      const x = xFor(i);
      const y = yFor(v);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Last price dot
    const lastX = xFor(n - 1);
    const lastY = yFor(closes[n - 1]);
    ctx.fillStyle = '#0ea5e9';
    ctx.beginPath();
    ctx.arc(lastX, lastY, 2.5, 0, Math.PI * 2);
    ctx.fill();
  }, [data, width, height]);

  if (loading) return <div className="text-sm text-muted-foreground">Loading chart…</div>;
  if (error) return <div className="text-sm text-red-600">{error}</div>;
  if (!data) return null;

  return (
    <canvas ref={canvasRef} width={width} height={height} />
  );
};

export default MiniOHLCChart;
