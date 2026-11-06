import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router'
import { messageOf } from '../../api/client'
import { DataTable, type Column, type SortState } from '../../components/DataTable'
import { Dialog } from '../../components/Dialog'
import { useDebounced } from '../../components/useDebounced'
import { hasRole, useMe } from '../../auth/context'
import { partnerApi, type Partner, type PartnerListParams } from './api'
import { STATUS_LABELS, type PartnerConfig } from './config'
import { PartnerForm } from './PartnerForm'
import { StatusBadge } from './StatusBadge'

const PAGE_SIZE = 25

/** List page for customers or vendors. */
export function PartnersPage({ cfg }: { cfg: PartnerConfig }) {
  const me = useMe()
  const canEdit = hasRole(me, 'editor')
  const navigate = useNavigate()
  const location = useLocation()
  const notice = (location.state as { notice?: string } | null)?.notice
  const queryClient = useQueryClient()
  const remote = useMemo(() => partnerApi(cfg), [cfg])
  const [search, setSearch] = useState('')
  const [active, setActive] = useState<PartnerListParams['active']>('true')
  const [status, setStatus] = useState<PartnerListParams['status']>('')
  const [sort, setSort] = useState<SortState>({ sort: 'legal_name', order: 'asc' })
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)

  const q = useDebounced(search)
  const params: PartnerListParams = { q, active, status, ...sort, page, page_size: PAGE_SIZE }
  const list = useQuery({
    queryKey: [cfg.kind, params],
    queryFn: () => remote.list(params),
    placeholderData: keepPreviousData,
  })
  const create = useMutation({
    mutationFn: remote.create,
    onSuccess: (p) => {
      void queryClient.invalidateQueries({ queryKey: [cfg.kind] })
      setAdding(false)
      void navigate(`${cfg.path}/${p.id}`, { state: { notice: `${p.legal_name} added.` } })
    },
  })

  const columns = useMemo<Column<Partner>[]>(() => {
    const cols: Column<Partner>[] = [
      { id: 'code', header: 'Code', accessorKey: 'code' },
      { id: 'legal_name', header: 'Legal name', accessorKey: 'legal_name' },
      { id: 'country_code', header: 'Country', accessorKey: 'country_code' },
      { id: 'default_currency', header: 'Currency', accessorKey: 'default_currency' },
      {
        id: 'status',
        header: 'Status',
        accessorKey: 'status',
        cell: ({ row }) =>
          row.original.is_active ? (
            <StatusBadge status={row.original.status} />
          ) : (
            <span className="badge badge-admin">Removed</span>
          ),
      },
      { id: 'payment_term_code', header: 'Payment terms', enableSorting: false, accessorFn: (p) => p.payment_term_code ?? '—' },
      { id: 'incoterm_code', header: 'Incoterm', enableSorting: false, accessorFn: (p) => p.incoterm_code ?? '—' },
    ]
    if (cfg.hasLeadTime) {
      cols.push({
        id: 'lead_time_days',
        header: 'Lead time',
        enableSorting: false,
        accessorFn: (p) => (p.lead_time_days != null ? `${String(p.lead_time_days)} d` : '—'),
      })
    }
    return cols
  }, [cfg])

  return (
    <section className="stack">
      <div className="page-head">
        <div>
          <h1>{cfg.title}</h1>
          <p className="muted">{cfg.intro}</p>
        </div>
        {canEdit && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              create.reset()
              setAdding(true)
            }}
          >
            Add {cfg.singular.toLowerCase()}
          </button>
        )}
      </div>

      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}

      <div className="filters">
        <input
          type="search"
          placeholder="Search code or name"
          aria-label={`Search ${cfg.title.toLowerCase()}`}
          maxLength={100}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
        <select
          aria-label="Filter by business status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as PartnerListParams['status'])
            setPage(1)
          }}
        >
          <option value="">Any status</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by record"
          value={active}
          onChange={(e) => {
            setActive(e.target.value as PartnerListParams['active'])
            setPage(1)
          }}
        >
          <option value="true">Current</option>
          <option value="false">Removed</option>
          <option value="">All</option>
        </select>
      </div>

      {list.isError ? (
        <p className="error">{messageOf(list.error)}</p>
      ) : (
        <DataTable
          columns={columns}
          rows={list.data?.items ?? []}
          total={list.data?.total ?? 0}
          page={page}
          pageSize={PAGE_SIZE}
          sort={sort}
          loading={list.isFetching}
          onSortChange={(s) => {
            setSort(s)
            setPage(1)
          }}
          onPageChange={setPage}
          onRowClick={(p) => {
            void navigate(`${cfg.path}/${p.id}`)
          }}
          rowLabel={(p) => `${p.code} ${p.legal_name}`}
          emptyText={`No ${cfg.title.toLowerCase()} match.`}
        />
      )}

      <Dialog
        open={adding}
        title={`Add ${cfg.singular.toLowerCase()}`}
        onClose={() => {
          setAdding(false)
        }}
      >
        <PartnerForm
          cfg={cfg}
          submitLabel={`Add ${cfg.singular.toLowerCase()}`}
          busy={create.isPending}
          error={create.error ? messageOf(create.error) : null}
          onSubmit={(v) => {
            create.mutate(v)
          }}
        />
      </Dialog>
    </section>
  )
}
