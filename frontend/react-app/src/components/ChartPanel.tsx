import { useEffect, useRef } from 'react';
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type MouseEventParams,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { DecisionData, IndicatorsData, KlineData } from '../types';

interface ChartPanelProps {
  klines: KlineData[];
  indicators: IndicatorsData;
  decisions: DecisionData[];
  onBarSelect?: (kline: KlineData) => void;
}

function toTimestamp(input: string): UTCTimestamp {
  return Math.floor(new Date(input).getTime() / 1000) as UTCTimestamp;
}

export function ChartPanel({ klines, indicators, decisions, onBarSelect }: ChartPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const sma20Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const sma50Ref = useRef<ISeriesApi<'Line'> | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: '#071325' },
        textColor: '#94a3b8',
        fontFamily: 'IBM Plex Mono, monospace',
      },
      grid: {
        vertLines: { color: 'rgba(71, 85, 105, 0.25)' },
        horzLines: { color: 'rgba(71, 85, 105, 0.25)' },
      },
      rightPriceScale: {
        borderColor: 'rgba(71, 85, 105, 0.4)',
      },
      timeScale: {
        borderColor: 'rgba(71, 85, 105, 0.4)',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: {
          color: 'rgba(14, 165, 233, 0.6)',
          width: 1,
          style: 2,
          labelBackgroundColor: '#0ea5e9',
        },
        horzLine: {
          color: 'rgba(14, 165, 233, 0.6)',
          width: 1,
          style: 2,
          labelBackgroundColor: '#0ea5e9',
        },
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#14b8a6',
      downColor: '#f97316',
      borderVisible: true,
      wickUpColor: '#14b8a6',
      wickDownColor: '#f97316',
      borderUpColor: '#14b8a6',
      borderDownColor: '#f97316',
    });

    const sma20Series = chart.addSeries(LineSeries, {
      color: '#facc15',
      lineWidth: 1,
      title: 'SMA20',
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const sma50Series = chart.addSeries(LineSeries, {
      color: '#38bdf8',
      lineWidth: 1,
      title: 'SMA50',
      priceLineVisible: false,
      lastValueVisible: false,
    });

    chartRef.current = chart;
    candleRef.current = candleSeries;
    sma20Ref.current = sma20Series;
    sma50Ref.current = sma50Series;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      sma20Ref.current = null;
      sma50Ref.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onBarSelect || !klines.length) {
      return;
    }

    const handleClick = (param: MouseEventParams<Time>) => {
      if (!param.time) {
        return;
      }

      const timestampSeconds = Number(param.time);
      const timestampMs = timestampSeconds * 1000;
      const selected = klines.find((item) => {
        const openMs = item.open_time_ms ?? new Date(item.time).getTime();
        return openMs === timestampMs;
      });

      if (selected) {
        onBarSelect(selected);
      }
    };

    chart.subscribeClick(handleClick);
    return () => {
      chart.unsubscribeClick(handleClick);
    };
  }, [klines, onBarSelect]);

  useEffect(() => {
    const candleSeries = candleRef.current;
    const sma20Series = sma20Ref.current;
    const sma50Series = sma50Ref.current;
    const chart = chartRef.current;

    if (!candleSeries || !sma20Series || !sma50Series || !chart) {
      return;
    }

    if (!klines.length) {
      candleSeries.setData([]);
      sma20Series.setData([]);
      sma50Series.setData([]);
      return;
    }

    candleSeries.setData(
      klines.map((item) => ({
        time: toTimestamp(item.time),
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      })),
    );

    const makeLineData = (values: Array<number | null> | undefined): LineData<UTCTimestamp>[] => {
      if (!values || !values.length) {
        return [];
      }
      const result: LineData<UTCTimestamp>[] = [];
      for (let i = 0; i < values.length; i += 1) {
        const value = values[i];
        if (value === null || Number.isNaN(value)) {
          continue;
        }
        const source = klines[i];
        if (!source) {
          continue;
        }
        result.push({
          time: toTimestamp(source.time),
          value,
        });
      }
      return result;
    };

    sma20Series.setData(makeLineData(indicators.sma_20));
    sma50Series.setData(makeLineData(indicators.sma_50));

    createSeriesMarkers(
      candleSeries,
      decisions
        .filter((item) => item.decision !== 'HOLD')
        .map((item) => ({
          time: toTimestamp(item.time),
          position: item.decision.includes('BUY') ? 'belowBar' : 'aboveBar',
          color: item.decision.includes('BUY') ? '#14b8a6' : '#f97316',
          shape: item.decision.includes('BUY') ? 'arrowUp' : 'arrowDown',
          text: item.decision.replace('_', ' '),
        })),
    );

    chart.timeScale().fitContent();
  }, [decisions, indicators.sma_20, indicators.sma_50, klines]);

  return <div ref={containerRef} className="chart-canvas" />;
}
