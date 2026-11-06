import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation } from '@tanstack/react-query'
import { ApiError, messageOf } from '../../api/client'
import { ConfirmDialog, Dialog } from '../../components/Dialog'
import { Field, FormError } from '../../components/Field'
import { CountrySelect } from '../../components/CodeSelects'
import {
  addVendorCode,
  removeVendorCode,
  updateVendorCode,
  type VendorCode,
  type VendorCodeInput,
} from './api'

interface Props {
  customerId: string
  codes: VendorCode[]
  canEdit: boolean
  onChanged: (message: string) => void
  onConflict: () => void
}

const pair = (v: VendorCode) => `${v.parent_code} / ${v.child_code}`

/** Amazon parent/child vendor codes (several per customer). */
export function VendorCodesSection({ customerId, codes, canEdit, onChanged, onConflict }: Props) {
  const [editing, setEditing] = useState<VendorCode | 'new' | null>(null)
  const [removing, setRemoving] = useState<VendorCode | null>(null)
  const remove = useMutation({
    mutationFn: removeVendorCode,
    onSuccess: () => {
      setRemoving(null)
      onChanged('Vendor code removed.')
    },
    onError: (e) => {
      setRemoving(null)
      if (e instanceof ApiError && e.isConflict) onConflict()
    },
  })

  return (
    <section className="card stack" aria-labelledby="vendor-codes-h">
      <div className="section-head">
        <h2 id="vendor-codes-h">Amazon vendor codes</h2>
        {canEdit && (
          <button
            type="button"
            className="btn"
            onClick={() => {
              setEditing('new')
            }}
          >
            Add vendor code
          </button>
        )}
      </div>
      {codes.length === 0 ? (
        <p className="muted">No vendor codes yet.</p>
      ) : (
        <table className="data-table" aria-label="Vendor codes">
          <thead>
            <tr>
              <th>Parent code</th>
              <th>Child code</th>
              <th>Destination</th>
              {canEdit && <th aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {codes.map((v) => (
              <tr key={v.id} aria-label={pair(v)}>
                <td>{v.parent_code}</td>
                <td>{v.child_code}</td>
                <td>{v.destination_country ?? '—'}</td>
                {canEdit && (
                  <td className="row-actions">
                    <button
                      type="button"
                      className="btn btn-small"
                      onClick={() => {
                        setEditing(v)
                      }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      onClick={() => {
                        setRemoving(v)
                      }}
                    >
                      Remove
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {remove.error ? <FormError message={messageOf(remove.error)} /> : null}

      <Dialog
        open={editing !== null}
        title={editing === 'new' ? 'Add vendor code' : 'Edit vendor code'}
        onClose={() => {
          setEditing(null)
        }}
      >
        {editing !== null && (
          <VendorCodeForm
            customerId={customerId}
            code={editing === 'new' ? null : editing}
            onDone={(msg) => {
              setEditing(null)
              onChanged(msg)
            }}
            onConflict={() => {
              setEditing(null)
              onConflict()
            }}
          />
        )}
      </Dialog>
      <ConfirmDialog
        open={removing !== null}
        title="Remove vendor code"
        danger
        busy={remove.isPending}
        confirmLabel="Remove"
        message={removing ? <p>Remove vendor code {pair(removing)}?</p> : null}
        onConfirm={() => {
          if (removing) remove.mutate(removing)
        }}
        onCancel={() => {
          setRemoving(null)
        }}
      />
    </section>
  )
}

const part = z
  .string()
  .transform((v) => v.replace(/\s+/g, '').toUpperCase())
  .pipe(z.string().regex(/^[A-Z0-9_-]{2,20}$/, '2–20 letters, digits, - or _'))

const schema = z.object({
  parent_code: part,
  child_code: part,
  destination_country: z.string().transform((v) => (v === '' ? null : v)),
})
type In = z.input<typeof schema>

function VendorCodeForm(props: {
  customerId: string
  code: VendorCode | null
  onDone: (msg: string) => void
  onConflict: () => void
}) {
  const { code } = props
  const form = useForm<In, unknown, VendorCodeInput>({
    resolver: zodResolver(schema),
    defaultValues: {
      parent_code: code?.parent_code ?? '',
      child_code: code?.child_code ?? '',
      destination_country: code?.destination_country ?? '',
    },
  })
  const save = useMutation({
    mutationFn: (v: VendorCodeInput) =>
      code ? updateVendorCode(code, v) : addVendorCode(props.customerId, v),
    onSuccess: () => {
      props.onDone(code ? 'Vendor code saved.' : 'Vendor code added.')
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict && e.message.startsWith('Someone else')) {
        props.onConflict()
      }
    },
  })
  const errors = form.formState.errors

  return (
    <form
      className="stack"
      noValidate
      onSubmit={(e) => {
        void form.handleSubmit((v) => {
          save.mutate(v)
        })(e)
      }}
    >
      <div className="grid-2">
        <Field label="Parent vendor code" error={errors.parent_code?.message}>
          <input type="text" autoComplete="off" {...form.register('parent_code')} />
        </Field>
        <Field label="Child vendor code" error={errors.child_code?.message}>
          <input type="text" autoComplete="off" {...form.register('child_code')} />
        </Field>
      </div>
      <Field label="Destination country" error={errors.destination_country?.message} hint="Optional">
        <CountrySelect {...form.register('destination_country')} />
      </Field>
      <FormError message={save.error ? messageOf(save.error) : null} />
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>
          {code ? 'Save vendor code' : 'Add vendor code'}
        </button>
      </div>
    </form>
  )
}
