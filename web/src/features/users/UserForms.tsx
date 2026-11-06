import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ApiError, messageOf } from '../../api/client'
import { Field, FormError } from '../../components/Field'
import { ConfirmDialog } from '../../components/Dialog'
import { createUser, deactivateUser, updateUser, type User } from './api'
import type { Role } from '../../auth/context'

const DOMAIN = 'buenavidatrading.com'
const ROLES: { value: Role; label: string }[] = [
  { value: 'viewer', label: 'Viewer (read-only)' },
  { value: 'editor', label: 'Editor (add, edit, remove, imports)' },
  { value: 'admin', label: 'Admin (everything + users)' },
]

const displayName = z
  .string()
  .trim()
  .max(200, 'At most 200 characters')
  .transform((v) => (v === '' ? null : v))

const createSchema = z.object({
  email: z
    .email({ message: 'Enter a valid email address' })
    .trim()
    .toLowerCase()
    .max(254)
    .refine((v) => v.endsWith(`@${DOMAIN}`), `Must be an @${DOMAIN} address`),
  display_name: displayName,
  role: z.enum(['viewer', 'editor', 'admin']),
})
type CreateInput = z.input<typeof createSchema>
type CreateOutput = z.output<typeof createSchema>

export function CreateUserForm({ onDone }: { onDone: (u: User) => void }) {
  const queryClient = useQueryClient()
  const form = useForm<CreateInput, unknown, CreateOutput>({
    resolver: zodResolver(createSchema),
    defaultValues: { email: '', display_name: '', role: 'viewer' },
  })
  const create = useMutation({
    mutationFn: createUser,
    onSuccess: (u) => {
      void queryClient.invalidateQueries({ queryKey: ['users'] })
      onDone(u)
    },
  })
  const errors = form.formState.errors

  return (
    <form
      className="stack"
      noValidate
      onSubmit={(e) => {
        void form.handleSubmit((v) => {
          create.mutate(v)
        })(e)
      }}
    >
      <Field label="Email" error={errors.email?.message} hint={`Must be an @${DOMAIN} Google account`}>
        <input type="email" autoComplete="off" {...form.register('email')} />
      </Field>
      <Field label="Display name" error={errors.display_name?.message}>
        <input type="text" {...form.register('display_name')} />
      </Field>
      <Field label="Role" error={errors.role?.message}>
        <select {...form.register('role')}>
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </Field>
      <FormError message={create.error ? messageOf(create.error) : null} />
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={create.isPending}>
          Add user
        </button>
      </div>
    </form>
  )
}

const editSchema = z.object({
  display_name: displayName,
  role: z.enum(['viewer', 'editor', 'admin']),
})
type EditInput = z.input<typeof editSchema>
type EditOutput = z.output<typeof editSchema>

interface EditProps {
  user: User
  isSelf: boolean
  onSaved: (u: User) => void
  onConflict: () => void
}

export function EditUserForm({ user, isSelf, onSaved, onConflict }: EditProps) {
  const queryClient = useQueryClient()
  const [confirming, setConfirming] = useState(false)
  const form = useForm<EditInput, unknown, EditOutput>({
    resolver: zodResolver(editSchema),
    defaultValues: { display_name: user.display_name ?? '', role: user.role },
  })

  const done = (u: User) => {
    void queryClient.invalidateQueries({ queryKey: ['users'] })
    onSaved(u)
  }
  const handleError = (e: unknown) => {
    if (e instanceof ApiError && e.isConflict) onConflict()
  }
  const save = useMutation({
    mutationFn: (v: EditOutput) => updateUser(user.id, { version: user.version, ...v }),
    onSuccess: done,
    onError: handleError,
  })
  const remove = useMutation({
    mutationFn: () => deactivateUser(user),
    onSuccess: (u) => {
      setConfirming(false)
      done(u)
    },
    onError: (e) => {
      setConfirming(false)
      handleError(e)
    },
  })
  const reactivate = useMutation({
    mutationFn: () => updateUser(user.id, { version: user.version, is_active: true }),
    onSuccess: done,
    onError: handleError,
  })
  const error = save.error ?? remove.error ?? reactivate.error
  const errors = form.formState.errors

  return (
    <div className="stack">
      <dl className="kv">
        <dt>Email</dt>
        <dd>{user.email}</dd>
        <dt>Status</dt>
        <dd>{user.is_active ? 'Active' : 'Removed (cannot sign in)'}</dd>
        <dt>Last sign-in</dt>
        <dd>{user.last_login_at ? new Date(user.last_login_at).toLocaleString() : 'Never'}</dd>
      </dl>
      <form
        className="stack"
        noValidate
        onSubmit={(e) => {
          void form.handleSubmit((v) => {
            save.mutate(v)
          })(e)
        }}
      >
        <Field label="Display name" error={errors.display_name?.message}>
          <input type="text" {...form.register('display_name')} />
        </Field>
        <Field
          label="Role"
          error={errors.role?.message}
          hint={isSelf ? "You can't change your own role." : undefined}
        >
          <select disabled={isSelf} {...form.register('role')}>
            {ROLES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </Field>
        <FormError message={error ? messageOf(error) : null} />
        <div className="actions">
          {user.is_active ? (
            <button
              type="button"
              className="btn btn-danger"
              disabled={isSelf}
              onClick={() => {
                setConfirming(true)
              }}
            >
              Remove user
            </button>
          ) : (
            <button
              type="button"
              className="btn"
              disabled={reactivate.isPending}
              onClick={() => {
                reactivate.mutate()
              }}
            >
              Reactivate
            </button>
          )}
          <span className="spacer" />
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            Save changes
          </button>
        </div>
      </form>
      <ConfirmDialog
        open={confirming}
        title="Remove user"
        danger
        busy={remove.isPending}
        confirmLabel="Remove"
        message={
          <p>
            <strong>{user.email}</strong> will no longer be able to sign in, and any open session
            ends now. You can reactivate the user later.
          </p>
        }
        onConfirm={() => {
          remove.mutate()
        }}
        onCancel={() => {
          setConfirming(false)
        }}
      />
    </div>
  )
}
