import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import type { QuoteBar } from "../lib/api";

interface Props {
  bars: QuoteBar[];
  height?: number;
}

export function PriceChart({ bars, height = 320 }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { color: "#0b0d10" },
        textColor: "#a0a8b4",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        fontSize: 11,
      },
      grid: {
        horzLines: { color: "#171b22" },
        vertLines: { color: "#171b22" },
      },
      rightPriceScale: { borderColor: "#22283340" },
      timeScale: { borderColor: "#22283340", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#2cb67d",
      downColor: "#ef4a53",
      borderUpColor: "#2cb67d",
      borderDownColor: "#ef4a53",
      wickUpColor: "#2cb67d",
      wickDownColor: "#ef4a53",
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver(() => {
      if (containerRef.current && chart) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    const data = bars.map((b) => ({
      time: (new Date(b.timestamp).getTime() / 1000) as UTCTimestamp,
      open: b.open, high: b.high, low: b.low, close: b.close,
    }));
    series.setData(data);
    if (data.length && chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [bars]);

  return <div ref={containerRef} style={{ width: "100%", height }} />;
}
