import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation } from '@tanstack/react-query'
import { ApiError, messageOf } from '../../api/client'
import { Field, FormError } from '../../components/Field'
import { ConfirmDialog, Dialog } from '../../components/Dialog'
import { CountrySelect } from '../../components/CodeSelects'
import {
  ADDRESS_TYPE_LABELS,
  addAddress,
  formatAddress,
  removeAddress,
  updateAddress,
  type Address,
  type AddressInput,
  type AddressType,
} from './api'
import { isoCountry, optionalText, requiredText } from './validation'

interface Props {
  partyId: string
  addresses: Address[]
  types: AddressType[]
  canEdit: boolean
  onChanged: (message: string) => void
  onConflict: () => void
}

export function AddressesSection({ partyId, addresses, types, canEdit, onChanged, onConflict }: Props) {
  const [editing, setEditing] = useState<Address | 'new' | null>(null)
  const [removing, setRemoving] = useState<Address | null>(null)
  const remove = useMutation({
    mutationFn: removeAddress,
    onSuccess: () => {
      setRemoving(null)
      onChanged('Address removed.')
    },
    onError: (e) => {
      setRemoving(null)
      if (e instanceof ApiError && e.isConflict) onConflict()
    },
  })

  return (
    <section className="card stack" aria-labelledby="addresses-h">
      <div className="section-head">
        <h2 id="addresses-h">Addresses</h2>
        {canEdit && (
          <button
            type="button"
            className="btn"
            onClick={() => {
              setEditing('new')
            }}
          >
            Add address
          </button>
        )}
      </div>
      {addresses.length === 0 ? (
        <p className="muted">No addresses yet.</p>
      ) : (
        <table className="data-table" aria-label="Addresses">
          <thead>
            <tr>
              <th>Type</th>
              <th>Address</th>
              <th>Country</th>
              {canEdit && <th aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {addresses.map((a) => (
              <tr key={a.id} aria-label={`${ADDRESS_TYPE_LABELS[a.address_type]}: ${formatAddress(a)}`}>
                <td>{ADDRESS_TYPE_LABELS[a.address_type]}</td>
                <td className="wrap">{formatAddress(a)}</td>
                <td>{a.country_code}</td>
                {canEdit && (
                  <td className="row-actions">
                    <button
                      type="button"
                      className="btn btn-small"
                      onClick={() => {
                        setEditing(a)
                      }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      onClick={() => {
                        setRemoving(a)
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
        title={editing === 'new' ? 'Add address' : 'Edit address'}
        onClose={() => {
          setEditing(null)
        }}
      >
        {editing !== null && (
          <AddressForm
            partyId={partyId}
            address={editing === 'new' ? null : editing}
            types={types}
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
        title="Remove address"
        danger
        busy={remove.isPending}
        confirmLabel="Remove"
        message={removing ? <p>Remove “{formatAddress(removing)}”?</p> : null}
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

const schema = z.object({
  address_type: z.enum(['registered', 'billing', 'warehouse', 'shipping', 'pickup', 'factory']),
  line1: requiredText(200, 'Address line 1'),
  line2: optionalText(200),
  postal_code: optionalText(20),
  city: requiredText(100, 'City'),
  region: optionalText(100),
  country_code: isoCountry,
})
type In = z.input<typeof schema>

function AddressForm(props: {
  partyId: string
  address: Address | null
  types: AddressType[]
  onDone: (msg: string) => void
  onConflict: () => void
}) {
  const { address } = props
  const form = useForm<In, unknown, AddressInput>({
    resolver: zodResolver(schema),
    defaultValues: {
      address_type: address?.address_type ?? props.types[0],
      line1: address?.line1 ?? '',
      line2: address?.line2 ?? '',
      postal_code: address?.postal_code ?? '',
      city: address?.city ?? '',
      region: address?.region ?? '',
      country_code: address?.country_code ?? '',
    },
  })
  const save = useMutation({
    mutationFn: (v: AddressInput) => (address ? updateAddress(address, v) : addAddress(props.partyId, v)),
    onSuccess: () => {
      props.onDone(address ? 'Address saved.' : 'Address added.')
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict) props.onConflict()
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
      <Field label="Type" error={errors.address_type?.message}>
        <select {...form.register('address_type')}>
          {props.types.map((t) => (
            <option key={t} value={t}>
              {ADDRESS_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Address line 1" error={errors.line1?.message}>
        <input type="text" {...form.register('line1')} />
      </Field>
      <Field label="Address line 2" error={errors.line2?.message}>
        <input type="text" {...form.register('line2')} />
      </Field>
      <div className="grid-2">
        <Field label="Postal code" error={errors.postal_code?.message}>
          <input type="text" {...form.register('postal_code')} />
        </Field>
        <Field label="City" error={errors.city?.message}>
          <input type="text" {...form.register('city')} />
        </Field>
      </div>
      <div className="grid-2">
        <Field label="Region / state" error={errors.region?.message}>
          <input type="text" {...form.register('region')} />
        </Field>
        <Field label="Country" error={errors.country_code?.message}>
          <CountrySelect {...form.register('country_code')} />
        </Field>
      </div>
      <FormError message={save.error ? messageOf(save.error) : null} />
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>
          {address ? 'Save address' : 'Add address'}
        </button>
      </div>
    </form>
  )
}
