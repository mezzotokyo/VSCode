export interface PhysicsParameters {
  drag_coefficient?: number
}

export interface SimulateRequest {
  velocity_kmph: number
  angle_deg: number
  dt: number
  adaptive: boolean
  parameters?: PhysicsParameters
}

export interface TrajectoryPoint {
  t: number
  x: number
  y: number
  vx: number
  vy: number
  speed: number
}

export interface SimulateResult {
  ideal_range: number
  ground_range: number
  flight_time: number
  impact_speed: number
  landed: boolean
  timed_out: boolean
  steps: number
  timestep_min: number | null
  timestep_max: number | null
}

export interface SimulateResponse {
  input: SimulateRequest
  result: SimulateResult
  trajectory: TrajectoryPoint[]
}
