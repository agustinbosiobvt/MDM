import { STATUS_LABELS, type PartnerStatus } from './config'

export function StatusBadge({ status }: { status: PartnerStatus }) {
  return <span className={`badge status-${status}`}>{STATUS_LABELS[status]}</span>
}
