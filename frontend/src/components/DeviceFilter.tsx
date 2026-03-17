import { Filter } from 'lucide-react'

interface Props {
  device: string
  onChange: (device: string) => void
  devices: string[]
}

export function DeviceFilter({ device, onChange, devices }: Props) {
  return (
    <div className="device-filter">
      <Filter size={14} />
      <select value={device} onChange={e => onChange(e.target.value)}>
        <option value="">All devices</option>
        {devices.map(d => (
          <option key={d} value={d}>{d}</option>
        ))}
      </select>
    </div>
  )
}
