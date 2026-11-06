import {
  flexRender,
  rowSortingFeature,
  tableFeatures,
  useTable,
  type ColumnDef,
  type RowData,
  type SortingState,
} from '@tanstack/react-table'

// TanStack Table v9: tables declare the features they use. Ours sort server-side.
const features = tableFeatures({ rowSortingFeature })
type Features = typeof features

/** Column definition for DataTable rows of type T. */
export type Column<T extends RowData> = ColumnDef<Features, T>

export interface SortState {
  sort: string
  order: 'asc' | 'desc'
}

interface Props<T extends RowData> {
  columns: Column<T>[]
  rows: T[]
  total: number
  page: number
  pageSize: number
  sort: SortState
  loading?: boolean
  onSortChange: (s: SortState) => void
  onPageChange: (page: number) => void
  onRowClick?: (row: T) => void
  rowLabel?: (row: T) => string
  emptyText?: string
  /** Accessible name of the table (needed when a page has several tables). */
  ariaLabel?: string
}

/** Server-side table: sorting and paging are sent to the API, not done in the browser. */
export function DataTable<T extends RowData>(props: Props<T>) {
  const { columns, rows, total, page, pageSize, sort, loading, onRowClick, rowLabel } = props
  const sorting: SortingState = [{ id: sort.sort, desc: sort.order === 'desc' }]

  const table = useTable({
    features,
    data: rows,
    columns,
    state: { sorting },
    manualSorting: true,
  })

  const pages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="table-wrap">
      <table className="data-table" aria-busy={loading} aria-label={props.ariaLabel}>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => {
                const canSort = header.column.getCanSort()
                const active = sort.sort === header.column.id
                const ariaSort = active ? (sort.order === 'asc' ? 'ascending' : 'descending') : 'none'
                return (
                  <th key={header.id} aria-sort={canSort ? ariaSort : undefined}>
                    {canSort ? (
                      <button
                        type="button"
                        className="th-sort"
                        onClick={() => {
                          props.onSortChange({
                            sort: header.column.id,
                            order: active && sort.order === 'asc' ? 'desc' : 'asc',
                          })
                        }}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <span className="sort-mark">{active ? (sort.order === 'asc' ? '▲' : '▼') : ''}</span>
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className={onRowClick ? 'clickable' : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              aria-label={rowLabel?.(row.original)}
              onClick={() => onRowClick?.(row.original)}
              onKeyDown={(e) => {
                if (onRowClick && (e.key === 'Enter' || e.key === ' ')) {
                  e.preventDefault()
                  onRowClick(row.original)
                }
              }}
            >
              {row.getAllCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && !loading && (
            <tr>
              <td colSpan={columns.length} className="muted empty">
                {props.emptyText ?? 'Nothing found.'}
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div className="pager">
        <span className="muted">
          {total.toLocaleString('en-US')} {total === 1 ? 'record' : 'records'}
        </span>
        <button
          type="button"
          className="btn"
          disabled={page <= 1}
          onClick={() => {
            props.onPageChange(page - 1)
          }}
        >
          Previous
        </button>
        <span>
          Page {page} of {pages}
        </span>
        <button
          type="button"
          className="btn"
          disabled={page >= pages}
          onClick={() => {
            props.onPageChange(page + 1)
          }}
        >
          Next
        </button>
      </div>
    </div>
  )
}
