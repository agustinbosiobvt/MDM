import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { ApiError, messageOf } from '../../api/client'
import { ConfirmDialog, Dialog } from '../../components/Dialog'
import { Field, FormError } from '../../components/Field'
import { hasRole, useMe } from '../../auth/context'
import { useCountries, useIncoterms, usePaymentTerms } from '../lookups/lookups'
import { AddressesSection } from '../parties/Addresses'
import { ContactsSection } from '../parties/Contacts'
import { partnerApi, type PartnerDetail } from './api'
import type { PartnerConfig } from './config'
import { PartnerForm } from './PartnerForm'
import { StatusBadge } from './StatusBadge'
import { VendorCodesSection } from './VendorCodes'
import { PriceListSection } from '../pricelists/PriceListSection'

const CONFLICT = 'Someone else changed this record. The page has been reloaded — check and try again.'

/** Detail page for one customer or vendor. */
export function PartnerDetailPage({ cfg }: { cfg: PartnerConfig }) {
  const { id = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const me = useMe()
  const queryClient = useQueryClient()
  const remote = useMemo(() => partnerApi(cfg), [cfg])
  const navState = location.state as { notice?: string; revision?: number } | null
  const [notice, setNotice] = useState<string | null>(navState?.notice ?? null)
  const partner = useQuery({ queryKey: [cfg.kind, 'one', id], queryFn: () => remote.get(id) })

  const refresh = (message: string) => {
    setNotice(message)
    void queryClient.invalidateQueries({ queryKey: [cfg.kind] })
  }
  const conflict = () => {
    refresh(CONFLICT)
  }

  if (partner.isPending) return <p className="muted">Loading…</p>
  if (partner.isError) {
    const missing = partner.error instanceof ApiError && partner.error.status === 404
    return (
      <section className="stack">
        <h1>{missing ? `${cfg.singular} not found` : `Could not load the ${cfg.kind}`}</h1>
        <p className="muted">{missing ? 'It may have been deleted.' : messageOf(partner.error)}</p>
        <Link to={cfg.path}>Back to the list</Link>
      </section>
    )
  }

  const p = partner.data
  const canEdit = hasRole(me, 'editor') && p.is_active

  return (
    <section className="stack">
      <Link to={cfg.path} className="back-link">
        ← All {cfg.title.toLowerCase()}
      </Link>
      <div className="page-head">
        <div>
          <h1>
            {p.legal_name}{' '}
            {p.is_active ? (
              <StatusBadge status={p.status} />
            ) : (
              <span className="badge badge-admin">Removed</span>
            )}
          </h1>
          <p className="muted">
            {p.code}
            {p.trade_name ? ` · ${p.trade_name}` : ''}
          </p>
        </div>
        <PartnerActions
          cfg={cfg}
          partner={p}
          isEditor={hasRole(me, 'editor')}
          isAdmin={hasRole(me, 'admin')}
          onChanged={refresh}
          onConflict={conflict}
          onDeleted={(msg) => {
            void queryClient.invalidateQueries({ queryKey: [cfg.kind] })
            void navigate(cfg.path, { state: { notice: msg } })
          }}
        />
      </div>

      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}

      <IdentityCard cfg={cfg} partner={p} />
      <AddressesSection
        partyId={p.id}
        addresses={p.addresses}
        types={cfg.addressTypes}
        canEdit={canEdit}
        onChanged={refresh}
        onConflict={conflict}
      />
      <ContactsSection
        partyId={p.id}
        contacts={p.contacts}
        canEdit={canEdit}
        withRoles={cfg.contactRoles}
        onChanged={refresh}
        onConflict={conflict}
      />
      {cfg.hasVendorCodes && (
        <VendorCodesSection
          customerId={p.id}
          codes={p.vendor_codes ?? []}
          canEdit={canEdit}
          onChanged={refresh}
          onConflict={conflict}
        />
      )}
      <PriceListSection
        partyId={p.id}
        basePath={`${cfg.path}/${p.id}`}
        partyActive={p.is_active}
        canEdit={hasRole(me, 'editor')}
        initialRevision={navState?.revision}
      />
    </section>
  )
}

function IdentityCard({ cfg, partner: p }: { cfg: PartnerConfig; partner: PartnerDetail }) {
  const countries = useCountries()
  const terms = usePaymentTerms()
  const incoterms = useIncoterms()
  const nameOf = (list: { code: string; name: string }[] | undefined, code: string | null) =>
    code ? `${list?.find((x) => x.code === code)?.name ?? code} (${code})` : '—'

  return (
    <section className="card" aria-labelledby="identity-h">
      <h2 id="identity-h">Identity and terms</h2>
      <dl className="kv">
        <dt>Code</dt>
        <dd>{p.code}</dd>
        <dt>Legal name</dt>
        <dd>{p.legal_name}</dd>
        <dt>Trade name</dt>
        <dd>{p.trade_name ?? '—'}</dd>
        {cfg.hasEori && (
          <>
            <dt>EORI</dt>
            <dd>{p.eori ?? '—'}</dd>
          </>
        )}
        <dt>Country</dt>
        <dd>{nameOf(countries.data, p.country_code)}</dd>
        <dt>Default currency</dt>
        <dd>{p.default_currency}</dd>
        <dt>Payment terms</dt>
        <dd>{nameOf(terms.data, p.payment_term_code)}</dd>
        <dt>Incoterm</dt>
        <dd>{nameOf(incoterms.data, p.incoterm_code)}</dd>
        {cfg.hasLeadTime && (
          <>
            <dt>Lead time</dt>
            <dd>{p.lead_time_days != null ? `${String(p.lead_time_days)} days` : '—'}</dd>
          </>
        )}
        <dt>Last changed</dt>
        <dd>{new Date(p.updated_at).toLocaleString()}</dd>
      </dl>
    </section>
  )
}

interface ActionsProps {
  cfg: PartnerConfig
  partner: PartnerDetail
  isEditor: boolean
  isAdmin: boolean
  onChanged: (msg: string) => void
  onConflict: () => void
  onDeleted: (msg: string) => void
}

function PartnerActions({ cfg, partner: p, isEditor, isAdmin, onChanged, onConflict, onDeleted }: ActionsProps) {
  const remote = useMemo(() => partnerApi(cfg), [cfg])
  const noun = cfg.singular.toLowerCase()
  const [editing, setEditing] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [typed, setTyped] = useState('')
  const isStale = (e: unknown) => e instanceof ApiError && e.isConflict && e.message.startsWith('Someone else')

  const edit = useMutation({
    mutationFn: (v: Parameters<typeof remote.update>[1]) => remote.update(p, v),
    onSuccess: () => {
      setEditing(false)
      onChanged(`${cfg.singular} saved.`)
    },
    onError: (e) => {
      if (isStale(e)) {
        setEditing(false)
        onConflict()
      }
    },
  })
  const remove = useMutation({
    mutationFn: () => remote.remove(p),
    onSuccess: () => {
      setConfirmRemove(false)
      onChanged(`${p.legal_name} removed. It stays in the history and can be reactivated.`)
    },
    onError: (e) => {
      setConfirmRemove(false)
      if (isStale(e)) onConflict()
    },
  })
  const reactivate = useMutation({
    mutationFn: () => remote.update(p, { is_active: true }),
    onSuccess: () => {
      onChanged(`${p.legal_name} reactivated.`)
    },
    onError: (e) => {
      if (isStale(e)) onConflict()
    },
  })
  const destroy = useMutation({
    mutationFn: () => remote.deletePermanently(p, typed),
    onSuccess: () => {
      onDeleted(`${p.legal_name} was deleted permanently.`)
    },
  })
  const error = remove.error ?? reactivate.error

  if (!isEditor) return null
  return (
    <div className="stack-tight">
      <div className="actions">
        {p.is_active ? (
          <>
            <button
              type="button"
              className="btn"
              onClick={() => {
                edit.reset()
                setEditing(true)
              }}
            >
              Edit {noun}
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => {
                setConfirmRemove(true)
              }}
            >
              Remove {noun}
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
      {error ? <FormError message={messageOf(error)} /> : null}

      <Dialog
        open={editing}
        title={`Edit ${noun}`}
        onClose={() => {
          setEditing(false)
        }}
      >
        {editing && (
          <PartnerForm
            cfg={cfg}
            partner={p}
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
        title={`Remove ${noun}`}
        danger
        busy={remove.isPending}
        confirmLabel="Remove"
        message={
          <p>
            Remove <strong>{p.legal_name}</strong>? It disappears from lists but stays in the
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
        title={`Delete ${noun} permanently`}
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
            This deletes <strong>{p.legal_name}</strong> with its addresses, contacts
            {cfg.hasVendorCodes ? ' and vendor codes' : ''}. It can&apos;t be undone (the audit log
            keeps a copy).
          </p>
          <Field label={`Type ${p.code} to confirm`}>
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
              disabled={typed.trim().toUpperCase() !== p.code || destroy.isPending}
            >
              Delete permanently
            </button>
          </div>
        </form>
      </Dialog>
    </div>
  )
}
