import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { simulate } from './api'
import { TrajectoryChart } from './components/TrajectoryChart'
import type { SimulateRequest, SimulateResponse } from './types'
import './App.css'

const INITIAL_REQUEST: SimulateRequest = {
  velocity_kmph: 170,
  angle_deg: 35,
  dt: 0.01,
  adaptive: false,
}

function format(value: number, digits = 2): string {
  return value.toFixed(digits)
}

export default function App() {
  const [form, setForm] = useState<SimulateRequest>(INITIAL_REQUEST)
  const [data, setData] = useState<SimulateResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const run = useCallback(async (request: SimulateRequest) => {
    setLoading(true)
    setError(null)
    try {
      setData(await simulate(request))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void run(INITIAL_REQUEST)
  }, [run])

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void run(form)
  }

  const result = data?.result ?? null
  const trajectory = data?.trajectory ?? []
  const reduction =
    result && result.ideal_range > 0
      ? ((result.ideal_range - result.ground_range) / result.ideal_range) * 100
      : 0

  return (
    <main className="app">
      <header className="header">
        <h1>Range Calculator Web</h1>
        <p className="subtitle">
          弾道シミュレーション（抗力あり RK4）をブラウザで可視化します。
        </p>
      </header>

      <div className="layout">
        <form className="panel controls" onSubmit={handleSubmit}>
          <h2>Launch conditions</h2>

          <label className="field">
            <span>
              初速 <b>{format(form.velocity_kmph, 1)}</b> km/h
            </span>
            <input
              type="range"
              min={10}
              max={400}
              step={1}
              value={form.velocity_kmph}
              onChange={(event) =>
                setForm({ ...form, velocity_kmph: Number(event.target.value) })
              }
            />
          </label>

          <label className="field">
            <span>
              発射角 <b>{format(form.angle_deg, 1)}</b> deg
            </span>
            <input
              type="range"
              min={1}
              max={89}
              step={1}
              value={form.angle_deg}
              onChange={(event) =>
                setForm({ ...form, angle_deg: Number(event.target.value) })
              }
            />
          </label>

          <label className="field inline">
            <span>刻み幅 dt (s)</span>
            <input
              type="number"
              min={0.0001}
              max={1}
              step={0.001}
              value={form.dt}
              onChange={(event) => setForm({ ...form, dt: Number(event.target.value) })}
            />
          </label>

          <label className="field checkbox">
            <input
              type="checkbox"
              checked={form.adaptive}
              onChange={(event) =>
                setForm({ ...form, adaptive: event.target.checked })
              }
            />
            <span>adaptive 刻み（安定性上限で自動短縮）</span>
          </label>

          <button type="submit" disabled={loading}>
            {loading ? '計算中...' : 'シミュレーション実行'}
          </button>

          {error && <p className="error">エラー: {error}</p>}
        </form>

        <section className="panel results">
          <h2>Result</h2>
          {!result ? (
            <p className="placeholder">
              {loading ? '計算中...' : 'シミュレーションを実行してください。'}
            </p>
          ) : (
            <>
              {result.timed_out && (
                <p className="warning">
                  時間上限に達しました。着弾前に計算が終了しています。
                </p>
              )}
              <dl className="metrics">
                <div>
                  <dt>理想射程（抗力なし）</dt>
                  <dd>{format(result.ideal_range)} m</dd>
                </div>
                <div>
                  <dt>実射程（抗力あり）</dt>
                  <dd>{format(result.ground_range)} m</dd>
                </div>
                <div>
                  <dt>到達距離の低減率</dt>
                  <dd>{format(reduction, 1)} %</dd>
                </div>
                <div>
                  <dt>飛行時間</dt>
                  <dd>{format(result.flight_time)} s</dd>
                </div>
                <div>
                  <dt>着弾速度</dt>
                  <dd>{format(result.impact_speed)} m/s</dd>
                </div>
                <div>
                  <dt>積分ステップ数</dt>
                  <dd>{result.steps}</dd>
                </div>
                {result.timestep_min !== null && (
                  <div>
                    <dt>最短刻み</dt>
                    <dd>{result.timestep_min.toExponential(3)} s</dd>
                  </div>
                )}
                <div>
                  <dt>着弾</dt>
                  <dd>{result.landed ? 'yes' : 'no'}</dd>
                </div>
              </dl>
            </>
          )}
        </section>
      </div>

      <section className="panel chart-panel">
        <h2>Trajectory</h2>
        {result ? (
          <TrajectoryChart
            trajectory={trajectory}
            idealRange={result.ideal_range}
            groundRange={result.ground_range}
          />
        ) : (
          <p className="placeholder">軌跡はまだありません。</p>
        )}
      </section>
    </main>
  )
}
