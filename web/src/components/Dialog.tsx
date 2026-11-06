import { useEffect, useRef, type ReactNode } from 'react'

interface Props {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}

/** Native <dialog>: focus trapping, Esc and the backdrop come from the browser. */
export function Dialog({ open, title, onClose, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-label={title}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
    >
      {open && (
        <>
          <header className="dialog-head">
            <h2>{title}</h2>
            <button type="button" className="btn-icon" aria-label="Close" onClick={onClose}>
              ×
            </button>
          </header>
          <div className="dialog-body">{children}</div>
        </>
      )}
    </dialog>
  )
}

interface ConfirmProps {
  open: boolean
  title: string
  message: ReactNode
  confirmLabel: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog(p: ConfirmProps) {
  return (
    <Dialog open={p.open} title={p.title} onClose={p.onCancel}>
      <div className="stack">
        <div>{p.message}</div>
        <div className="actions">
          <button type="button" className="btn" onClick={p.onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className={p.danger ? 'btn btn-danger' : 'btn btn-primary'}
            disabled={p.busy}
            onClick={p.onConfirm}
          >
            {p.confirmLabel}
          </button>
        </div>
      </div>
    </Dialog>
  )
}
