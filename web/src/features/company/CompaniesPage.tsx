import { useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router'
import { messageOf } from '../../api/client'
import { DataTable, type Column, type SortState } from '../../components/DataTable'
import { Dialog } from '../../components/Dialog'
import { useDebounced } from '../../components/useDebounced'
import { hasRole, useMe } from '../../auth/context'
import { createCompany, listCompanies, type Company, type CompanyListParams } from './api'
import { CompanyForm } from './CompanyForm'

const PAGE_SIZE = 25

export function CompaniesPage() {
  const me = useMe()
  const canEdit = hasRole(me, 'editor')
  const navigate = useNavigate()
  const location = useLocation()
  const notice = (location.state as { notice?: string } | null)?.notice
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [active, setActive] = useState<CompanyListParams['active']>('true')
  const [sort, setSort] = useState<SortState>({ sort: 'legal_name', order: 'asc' })
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)

  const q = useDebounced(search)
  const params: CompanyListParams = { q, active, ...sort, page, page_size: PAGE_SIZE }
  const companies = useQuery({
    queryKey: ['companies', params],
    queryFn: () => listCompanies(params),
    placeholderData: keepPreviousData,
  })
  const create = useMutation({
    mutationFn: createCompany,
    onSuccess: (c) => {
      void queryClient.invalidateQueries({ queryKey: ['companies'] })
      setAdding(false)
      void navigate(`/company/${c.id}`, { state: { notice: `${c.legal_name} added.` } })
    },
  })

  const columns = useMemo<Column<Company>[]>(
    () => [
      { id: 'code', header: 'Code', accessorKey: 'code' },
      {
        id: 'legal_name',
        header: 'Legal name',
        accessorKey: 'legal_name', // an accessor makes the column sortable
        cell: ({ row }) => (
          <>
            {row.original.legal_name}{' '}
            {row.original.is_default && <span className="badge badge-editor">Default</span>}
          </>
        ),
      },
      { id: 'trade_name', header: 'Trade name', accessorFn: (c) => c.trade_name ?? '—' },
      { id: 'country_code', header: 'Country', accessorKey: 'country_code' },
      {
        id: 'is_active',
        header: 'Status',
        enableSorting: false,
        cell: ({ row }) => (row.original.is_active ? 'Active' : 'Removed'),
      },
    ],
    [],
  )

  return (
    <section className="stack">
      <div className="page-head">
        <div>
          <h1>Company</h1>
          <p className="muted">Buena Vida Trading&apos;s own legal entities. One is the default.</p>
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
            Add company
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
          aria-label="Search companies"
          maxLength={100}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
        <select
          aria-label="Filter by status"
          value={active}
          onChange={(e) => {
            setActive(e.target.value as CompanyListParams['active'])
            setPage(1)
          }}
        >
          <option value="true">Active</option>
          <option value="false">Removed</option>
          <option value="">All</option>
        </select>
      </div>

      {companies.isError ? (
        <p className="error">{messageOf(companies.error)}</p>
      ) : (
        <DataTable
          columns={columns}
          rows={companies.data?.items ?? []}
          total={companies.data?.total ?? 0}
          page={page}
          pageSize={PAGE_SIZE}
          sort={sort}
          loading={companies.isFetching}
          onSortChange={(s) => {
            setSort(s)
            setPage(1)
          }}
          onPageChange={setPage}
          onRowClick={(c) => {
            void navigate(`/company/${c.id}`)
          }}
          rowLabel={(c) => `${c.code} ${c.legal_name}`}
          emptyText="No companies match."
        />
      )}

      <Dialog
        open={adding}
        title="Add company"
        onClose={() => {
          setAdding(false)
        }}
      >
        <CompanyForm
          submitLabel="Add company"
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
