import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { ApiError, messageOf } from '../../api/client'
import { ConfirmDialog, Dialog } from '../../components/Dialog'
import { Field, FormError } from '../../components/Field'
import { hasRole, useMe } from '../../auth/context'
import { useCountries } from '../lookups/lookups'
import { AddressesSection } from '../parties/Addresses'
import { ContactsSection } from '../parties/Contacts'
import {
  deletePermanently,
  getCompany,
  makeDefault,
  removeCompany,
  updateCompany,
  type CompanyDetail,
} from './api'
import { CompanyForm } from './CompanyForm'

const CONFLICT = 'Someone else changed this record. The page has been reloaded — check and try again.'

export function CompanyDetailPage() {
  const { id = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const me = useMe()
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<string | null>(
    (location.state as { notice?: string } | null)?.notice ?? null,
  )
  const company = useQuery({ queryKey: ['companies', 'one', id], queryFn: () => getCompany(id) })

  const refresh = (message: string) => {
    setNotice(message)
    void queryClient.invalidateQueries({ queryKey: ['companies'] })
  }
  const conflict = () => {
    refresh(CONFLICT)
  }

  if (company.isPending) return <p className="muted">Loading…</p>
  if (company.isError) {
    const missing = company.error instanceof ApiError && company.error.status === 404
    return (
      <section className="stack">
        <h1>{missing ? 'Company not found' : 'Could not load the company'}</h1>
        <p className="muted">{missing ? 'It may have been deleted.' : messageOf(company.error)}</p>
        <Link to="/company">Back to the list</Link>
      </section>
    )
  }

  const c = company.data
  const canEdit = hasRole(me, 'editor') && c.is_active

  return (
    <section className="stack">
      <Link to="/company" className="back-link">
        ← All companies
      </Link>
      <div className="page-head">
        <div>
          <h1>
            {c.legal_name}{' '}
            {c.is_default && <span className="badge badge-editor">Default</span>}
            {!c.is_active && <span className="badge badge-admin">Removed</span>}
          </h1>
          <p className="muted">
            {c.code}
            {c.trade_name ? ` · ${c.trade_name}` : ''}
          </p>
        </div>
        <CompanyActions
          company={c}
          isEditor={hasRole(me, 'editor')}
          isAdmin={hasRole(me, 'admin')}
          onChanged={refresh}
          onConflict={conflict}
          onDeleted={(msg) => {
            void queryClient.invalidateQueries({ queryKey: ['companies'] })
            void navigate('/company', { state: { notice: msg } })
          }}
        />
      </div>

      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}

      <IdentityCard company={c} />
      <AddressesSection
        partyId={c.id}
        addresses={c.addresses}
        types={['registered', 'billing', 'warehouse']}
        canEdit={canEdit}
        onChanged={refresh}
        onConflict={conflict}
      />
      <ContactsSection
        partyId={c.id}
        contacts={c.contacts}
        canEdit={canEdit}
        onChanged={refresh}
        onConflict={conflict}
      />
    </section>
  )
}

function IdentityCard({ company: c }: { company: CompanyDetail }) {
  const countries = useCountries()
  const country = countries.data?.find((x) => x.code === c.country_code)?.name
  return (
    <section className="card" aria-labelledby="identity-h">
      <h2 id="identity-h">Identity</h2>
      <dl className="kv">
        <dt>Code</dt>
        <dd>{c.code}</dd>
        <dt>Legal name</dt>
        <dd>{c.legal_name}</dd>
        <dt>Trade name</dt>
        <dd>{c.trade_name ?? '—'}</dd>
        <dt>EORI</dt>
        <dd>{c.eori ?? '—'}</dd>
        <dt>Tax registration number</dt>
        <dd>{c.tax_registration_number ?? '—'}</dd>
        <dt>Country</dt>
        <dd>{country ? `${country} (${c.country_code})` : c.country_code}</dd>
        <dt>Last changed</dt>
        <dd>{new Date(c.updated_at).toLocaleString()}</dd>
      </dl>
    </section>
  )
}

interface ActionsProps {
  company: CompanyDetail
  isEditor: boolean
  isAdmin: boolean
  onChanged: (msg: string) => void
  onConflict: () => void
  onDeleted: (msg: string) => void
}

function CompanyActions({ company: c, isEditor, isAdmin, onChanged, onConflict, onDeleted }: ActionsProps) {
  const [editing, setEditing] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [typed, setTyped] = useState('')
  const handleError = (e: unknown) => {
    if (e instanceof ApiError && e.isConflict && e.message.startsWith('Someone else')) onConflict()
  }

  const edit = useMutation({
    mutationFn: (v: Parameters<typeof updateCompany>[1]) => updateCompany(c, v),
    onSuccess: () => {
      setEditing(false)
      onChanged('Company saved.')
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict && e.message.startsWith('Someone else')) {
        setEditing(false)
      }
      handleError(e)
    },
  })
  const setDefault = useMutation({
    mutationFn: () => makeDefault(c),
    onSuccess: () => {
      onChanged(`${c.legal_name} is now the default company.`)
    },
  })
  const remove = useMutation({
    mutationFn: () => removeCompany(c),
    onSuccess: () => {
      setConfirmRemove(false)
      onChanged(`${c.legal_name} removed. It stays in the history and can be reactivated.`)
    },
    onError: (e) => {
      setConfirmRemove(false)
      handleError(e)
    },
  })
  const reactivate = useMutation({
    mutationFn: () => updateCompany(c, { is_active: true }),
    onSuccess: () => {
      onChanged(`${c.legal_name} reactivated.`)
    },
    onError: handleError,
  })
  const destroy = useMutation({
    mutationFn: () => deletePermanently(c, typed),
    onSuccess: () => {
      onDeleted(`${c.legal_name} was deleted permanently.`)
    },
  })
  const error = setDefault.error ?? remove.error ?? reactivate.error

  if (!isEditor) return null
  return (
    <div className="stack-tight">
      <div className="actions">
        {c.is_active ? (
          <>
            <button
              type="button"
              className="btn"
              onClick={() => {
                edit.reset()
                setEditing(true)
              }}
            >
              Edit company
            </button>
            {!c.is_default && (
              <button
                type="button"
                className="btn"
                disabled={setDefault.isPending}
                onClick={() => {
                  setDefault.mutate()
                }}
              >
                Make default
              </button>
            )}
            <button
              type="button"
              className="btn btn-danger"
              disabled={c.is_default}
              title={c.is_default ? 'Make another company the default first' : undefined}
              onClick={() => {
                setConfirmRemove(true)
              }}
            >
              Remove company
            </button>
          </>
        ) : (
          <>
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
            {isAdmin && (
              <button
                type="button"
                className="btn btn-danger"
                onClick={() => {
                  setTyped('')
                  destroy.reset()
                  setConfirmDelete(true)
                }}
              >
                Delete permanently
              </button>
            )}
          </>
        )}
      </div>
      {c.is_default && c.is_active && (
        <p className="muted small">The default company can&apos;t be removed.</p>
      )}
      {error ? <FormError message={messageOf(error)} /> : null}

      <Dialog
        open={editing}
        title="Edit company"
        onClose={() => {
          setEditing(false)
        }}
      >
        {editing && (
          <CompanyForm
            company={c}
            submitLabel="Save changes"
            busy={edit.isPending}
            error={edit.error ? messageOf(edit.error) : null}
            onSubmit={(v) => {
              edit.mutate(v)
            }}
          />
        )}
      </Dialog>
      <ConfirmDialog
        open={confirmRemove}
        title="Remove company"
        danger
        busy={remove.isPending}
        confirmLabel="Remove"
        message={
          <p>
            Remove <strong>{c.legal_name}</strong>? It disappears from lists but stays in the
            database and the audit history; you can reactivate it later.
          </p>
        }
        onConfirm={() => {
          remove.mutate()
        }}
        onCancel={() => {
          setConfirmRemove(false)
        }}
      />
      <Dialog
        open={confirmDelete}
        title="Delete company permanently"
        onClose={() => {
          setConfirmDelete(false)
        }}
      >
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            destroy.mutate()
          }}
        >
          <p>
            This deletes <strong>{c.legal_name}</strong> with its addresses and contacts. It
            can&apos;t be undone (the audit log keeps a copy).
          </p>
          <Field label={`Type ${c.code} to confirm`}>
            <input
              type="text"
              autoComplete="off"
              value={typed}
              onChange={(e) => {
                setTyped(e.target.value)
              }}
            />
          </Field>
          <FormError message={destroy.error ? messageOf(destroy.error) : null} />
          <div className="actions">
            <button
              type="button"
              className="btn"
              onClick={() => {
                setConfirmDelete(false)
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-danger"
              disabled={typed.trim().toUpperCase() !== c.code || destroy.isPending}
            >
              Delete permanently
            </button>
          </div>
        </form>
      </Dialog>
    </div>
  )
}
