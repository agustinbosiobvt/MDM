import { useId, type ReactElement, cloneElement } from 'react'

interface Props {
  label: string
  error?: string
  hint?: string
  children: ReactElement<{ id?: string; 'aria-invalid'?: boolean; 'aria-describedby'?: string }>
}

/** Label + control + error, wired for accessibility (and for getByLabel in e2e tests). */
export function Field({ label, error, hint, children }: Props) {
  const id = useId()
  const msgId = `${id}-msg`
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {cloneElement(children, {
        id,
        'aria-invalid': error ? true : undefined,
        'aria-describedby': error || hint ? msgId : undefined,
      })}
      {error ? (
        <span id={msgId} className="field-error">
          {error}
        </span>
      ) : hint ? (
        <span id={msgId} className="muted small">
          {hint}
        </span>
      ) : null}
    </div>
  )
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <p className="form-error" role="alert">
      {message}
    </p>
  )
}
