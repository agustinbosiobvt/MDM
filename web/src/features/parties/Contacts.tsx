import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation } from '@tanstack/react-query'
import { ApiError, messageOf } from '../../api/client'
import { Field, FormError } from '../../components/Field'
import { ConfirmDialog, Dialog } from '../../components/Dialog'
import {
  CONTACT_ROLE_LABELS,
  addContact,
  removeContact,
  updateContact,
  type Contact,
  type ContactInput,
  type ContactRole,
} from './api'
import { email, optionalText, phone, requiredText } from './validation'

interface Props {
  partyId: string
  contacts: Contact[]
  canEdit: boolean
  /** Show the Sales / Logistics / Quality / Other role (vendor contacts). */
  withRoles?: boolean
  onChanged: (message: string) => void
  onConflict: () => void
}

const toInput = (c: Contact): ContactInput => ({
  name: c.name,
  role_title: c.role_title,
  email: c.email,
  phone: c.phone,
  is_primary: c.is_primary,
  contact_role: c.contact_role,
})

export function ContactsSection({ partyId, contacts, canEdit, withRoles = false, onChanged, onConflict }: Props) {
  const [editing, setEditing] = useState<Contact | 'new' | null>(null)
  const [removing, setRemoving] = useState<Contact | null>(null)
  const handleError = (e: unknown) => {
    if (e instanceof ApiError && e.isConflict) onConflict()
  }
  const remove = useMutation({
    mutationFn: removeContact,
    onSuccess: () => {
      setRemoving(null)
      onChanged('Contact removed.')
    },
    onError: (e) => {
      setRemoving(null)
      handleError(e)
    },
  })
  const primary = useMutation({
    mutationFn: (c: Contact) => updateContact(c, { ...toInput(c), is_primary: true }),
    onSuccess: (c) => {
      onChanged(`${c.name} is now the primary contact.`)
    },
    onError: handleError,
  })
  const error = remove.error ?? primary.error

  return (
    <section className="card stack" aria-labelledby="contacts-h">
      <div className="section-head">
        <h2 id="contacts-h">Contacts</h2>
        {canEdit && (
          <button
            type="button"
            className="btn"
            onClick={() => {
              setEditing('new')
            }}
          >
            Add contact
          </button>
        )}
      </div>
      {contacts.length === 0 ? (
        <p className="muted">No contacts yet.</p>
      ) : (
        <table className="data-table" aria-label="Contacts">
          <thead>
            <tr>
              <th>Name</th>
              {withRoles && <th>Contact role</th>}
              <th>Job title</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Primary</th>
              {canEdit && <th aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {contacts.map((c) => (
              <tr key={c.id} aria-label={c.name}>
                <td>{c.name}</td>
                {withRoles && <td>{c.contact_role ? CONTACT_ROLE_LABELS[c.contact_role] : '—'}</td>}
                <td>{c.role_title ?? '—'}</td>
                <td>{c.email ? <a href={`mailto:${c.email}`}>{c.email}</a> : '—'}</td>
                <td>{c.phone ?? '—'}</td>
                <td>{c.is_primary ? <span className="badge badge-editor">Primary</span> : ''}</td>
                {canEdit && (
                  <td className="row-actions">
                    {!c.is_primary && (
                      <button
                        type="button"
                        className="btn btn-small"
                        disabled={primary.isPending}
                        onClick={() => {
                          primary.mutate(c)
                        }}
                      >
                        Make primary
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-small"
                      onClick={() => {
                        setEditing(c)
                      }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      onClick={() => {
                        setRemoving(c)
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
      {error ? <FormError message={messageOf(error)} /> : null}

      <Dialog
        open={editing !== null}
        title={editing === 'new' ? 'Add contact' : 'Edit contact'}
        onClose={() => {
          setEditing(null)
        }}
      >
        {editing !== null && (
          <ContactForm
            partyId={partyId}
            contact={editing === 'new' ? null : editing}
            withRoles={withRoles}
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
        title="Remove contact"
        danger
        busy={remove.isPending}
        confirmLabel="Remove"
        message={removing ? <p>Remove {removing.name}?</p> : null}
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
  name: requiredText(200, 'Name'),
  role_title: optionalText(100),
  email,
  phone,
  is_primary: z.boolean(),
  contact_role: z
    .enum(['', 'sales', 'logistics', 'quality', 'other'])
    .transform((v): ContactRole | null => (v === '' ? null : v)),
})
type In = z.input<typeof schema>

function ContactForm(props: {
  partyId: string
  contact: Contact | null
  withRoles: boolean
  onDone: (msg: string) => void
  onConflict: () => void
}) {
  const { contact } = props
  const form = useForm<In, unknown, ContactInput>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: contact?.name ?? '',
      role_title: contact?.role_title ?? '',
      email: contact?.email ?? '',
      phone: contact?.phone ?? '',
      is_primary: contact?.is_primary ?? false,
      contact_role: contact?.contact_role ?? '',
    },
  })
  const save = useMutation({
    mutationFn: (v: ContactInput) => (contact ? updateContact(contact, v) : addContact(props.partyId, v)),
    onSuccess: () => {
      props.onDone(contact ? 'Contact saved.' : 'Contact added.')
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
      <Field label="Name" error={errors.name?.message}>
        <input type="text" {...form.register('name')} />
      </Field>
      {props.withRoles && (
        <Field label="Contact role" error={errors.contact_role?.message}>
          <select {...form.register('contact_role')}>
            <option value="">Not set</option>
            {Object.entries(CONTACT_ROLE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      )}
      <Field label="Job title" error={errors.role_title?.message} hint="e.g. Managing director, Accounts">
        <input type="text" {...form.register('role_title')} />
      </Field>
      <div className="grid-2">
        <Field label="Email" error={errors.email?.message}>
          <input type="email" {...form.register('email')} />
        </Field>
        <Field label="Phone" error={errors.phone?.message}>
          <input type="tel" {...form.register('phone')} />
        </Field>
      </div>
      <label className="checkbox">
        <input type="checkbox" {...form.register('is_primary')} /> Primary contact
      </label>
      <FormError message={save.error ? messageOf(save.error) : null} />
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={save.isPending}>
          {contact ? 'Save contact' : 'Add contact'}
        </button>
      </div>
    </form>
  )
}
