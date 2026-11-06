import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { messageOf } from '../../api/client'
import { DataTable, type Column, type SortState } from '../../components/DataTable'
import { Dialog } from '../../components/Dialog'
import { useDebounced } from '../../components/useDebounced'
import { useMe } from '../../auth/context'
import { getUser, listUsers, type User, type UserListParams } from './api'
import { CreateUserForm, EditUserForm } from './UserForms'

const PAGE_SIZE = 25

export function UsersPage() {
  const me = useMe()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [role, setRole] = useState<UserListParams['role']>('')
  const [active, setActive] = useState<UserListParams['active']>('true')
  const [sort, setSort] = useState<SortState>({ sort: 'email', order: 'asc' })
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  const [selected, setSelected] = useState<User | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const q = useDebounced(search)
  const params: UserListParams = { q, role, active, ...sort, page, page_size: PAGE_SIZE }
  const users = useQuery({
    queryKey: ['users', params],
    queryFn: () => listUsers(params),
    placeholderData: keepPreviousData,
  })

  const columns = useMemo<Column<User>[]>(
    () => [
      { id: 'email', header: 'Email', accessorKey: 'email' },
      {
        id: 'display_name',
        header: 'Name',
        accessorFn: (u) => u.display_name ?? '—',
      },
      { id: 'role', header: 'Role', accessorKey: 'role', cell: ({ row }) => <RoleBadge role={row.original.role} /> },
      {
        id: 'is_active',
        header: 'Status',
        enableSorting: false,
        cell: ({ row }) => (row.original.is_active ? 'Active' : 'Removed'),
      },
      {
        id: 'last_login_at',
        header: 'Last sign-in',
        accessorKey: 'last_login_at',
        cell: ({ row }) =>
          row.original.last_login_at ? new Date(row.original.last_login_at).toLocaleString() : 'Never',
      },
    ],
    [],
  )

  return (
    <section className="stack">
      <div className="page-head">
        <div>
          <h1>Users</h1>
          <p className="muted">Who can sign in, and with which role.</p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            setAdding(true)
          }}
        >
          Add user
        </button>
      </div>

      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}

      <div className="filters">
        <input
          type="search"
          placeholder="Search email or name"
          aria-label="Search users"
          maxLength={100}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value)
            setPage(1)
          }}
        />
        <select
          aria-label="Filter by role"
          value={role}
          onChange={(e) => {
            setRole(e.target.value as UserListParams['role'])
            setPage(1)
          }}
        >
          <option value="">All roles</option>
          <option value="admin">Admin</option>
          <option value="editor">Editor</option>
          <option value="viewer">Viewer</option>
        </select>
        <select
          aria-label="Filter by status"
          value={active}
          onChange={(e) => {
            setActive(e.target.value as UserListParams['active'])
            setPage(1)
          }}
        >
          <option value="true">Active</option>
          <option value="false">Removed</option>
          <option value="">All</option>
        </select>
      </div>

      {users.isError ? (
        <p className="error">{messageOf(users.error)}</p>
      ) : (
        <DataTable
          columns={columns}
          rows={users.data?.items ?? []}
          total={users.data?.total ?? 0}
          page={page}
          pageSize={PAGE_SIZE}
          sort={sort}
          loading={users.isFetching}
          onSortChange={(s) => {
            setSort(s)
            setPage(1)
          }}
          onPageChange={setPage}
          onRowClick={(u) => {
            setNotice(null)
            // Edit the current version, not the (possibly stale) list row.
            queryClient
              .query({ queryKey: ['users', 'one', u.id], queryFn: () => getUser(u.id), staleTime: 0 })
              .then(setSelected)
              .catch((e: unknown) => {
                setNotice(messageOf(e))
              })
          }}
          rowLabel={(u) => u.email}
          emptyText="No users match."
        />
      )}

      <Dialog
        open={adding}
        title="Add user"
        onClose={() => {
          setAdding(false)
        }}
      >
        <CreateUserForm
          onDone={(u) => {
            setAdding(false)
            setNotice(`${u.email} added as ${u.role}.`)
          }}
        />
      </Dialog>

      <Dialog
        open={selected !== null}
        title="User details"
        onClose={() => {
          setSelected(null)
        }}
      >
        {selected && (
          <EditUserForm
            key={`${selected.id}-${String(selected.version)}`}
            user={selected}
            isSelf={selected.id === me.id}
            onSaved={(u) => {
              setSelected(null)
              setNotice(`${u.email} saved.`)
            }}
            onConflict={() => {
              setSelected(null)
              setNotice('Someone else changed this record. The list has been reloaded — open it again.')
              void queryClient.invalidateQueries({ queryKey: ['users'] })
            }}
          />
        )}
      </Dialog>
    </section>
  )
}

function RoleBadge({ role }: { role: User['role'] }) {
  return <span className={`badge badge-${role}`}>{role}</span>
}
