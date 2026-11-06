import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ApiError, messageOf } from '../../api/client'
import { Dialog } from '../../components/Dialog'
import { Field, FormError } from '../../components/Field'
import { ISSUE_LABELS, formatAmount, updateLine, type Line } from './api'

interface Props {
  line: Line
  listIsDraft: boolean
  canEdit: boolean
  typeName: (code: string) => string
  onClose: () => void
  onSaved: (message: string) => void
  onConflict: () => void
}

/** One line: all its data and prices; category, brand and observations are editable, prices never. */
export function LineDialog({ line, listIsDraft, canEdit, typeName, onClose, onSaved, onConflict }: Props) {
  const [category, setCategory] = useState(line.category ?? '')
  const [brand, setBrand] = useState(line.brand ?? '')
  const [observations, setObservations] = useState(line.observations ?? '')
  const save = useMutation({
    mutationFn: (body: Parameters<typeof updateLine>[1]) => updateLine(line, body),
    onSuccess: (l) => {
      if (l.is_active === line.is_active) onSaved('Line saved.')
      else onSaved(l.is_active ? 'Line included.' : 'Line excluded.')
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isConflict && e.message.startsWith('Someone else')) onConflict()
    },
  })
  const tooLong = category.length > 100 || brand.length > 100 || observations.length > 2000

  return (
    <Dialog open title="Product details" onClose={onClose}>
      <div className="stack">
        <dl className="kv kv-wide">
          <dt>EAN</dt>
          <dd>{line.ean ?? '—'}</dd>
          {line.upc && (
            <>
              <dt>UPC</dt>
              <dd>{line.upc}</dd>
            </>
          )}
          <dt>ASIN</dt>
          <dd>{line.asin ?? '—'}</dd>
          <dt>Vendor SKU</dt>
          <dd>{line.vendor_sku ?? '—'}</dd>
          <dt>Description</dt>
          <dd className="wrap">{line.description ?? '—'}</dd>
          <dt>Case pack / MOQ</dt>
          <dd>
            {line.case_pack_qty ?? '—'} / {line.moq ?? '—'}
          </dd>
          <dt>Origin / HS code</dt>
          <dd>
            {line.country_of_origin ?? '—'} / {line.hs_code ?? '—'}
          </dd>
          {line.dimensions && Object.keys(line.dimensions).length > 0 && (
            <>
              <dt>Dimensions</dt>
              <dd>
                {Object.entries(line.dimensions)
                  .map(([col, v]) => `${col}: ${v ?? '—'}`)
                  .join(' · ')}
              </dd>
            </>
          )}
          <dt>Prices</dt>
          <dd>
            {line.prices.length === 0
              ? '—'
              : line.prices.map((p) => (
                  <div key={`${p.price_type}-${p.currency}`}>
                    {typeName(p.price_type)}: <span className="num">{formatAmount(p.amount)}</span>{' '}
                    {p.currency}
                  </div>
                ))}
          </dd>
          {line.issues.length > 0 && (
            <>
              <dt>Warnings</dt>
              <dd>{line.issues.map((i) => ISSUE_LABELS[i] ?? i).join(', ')}</dd>
            </>
          )}
        </dl>

        {canEdit ? (
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault()
              save.mutate({
                category: category.trim() || null,
                brand: brand.trim() || null,
                observations: observations.trim() || null,
              })
            }}
          >
            <div className="grid-2">
              <Field label="Category" error={category.length > 100 ? 'At most 100 characters' : undefined}>
                <input
                  type="text"
                  value={category}
                  onChange={(e) => {
                    setCategory(e.target.value)
                  }}
                />
              </Field>
              <Field label="Brand" error={brand.length > 100 ? 'At most 100 characters' : undefined}>
                <input
                  type="text"
                  value={brand}
                  onChange={(e) => {
                    setBrand(e.target.value)
                  }}
                />
              </Field>
            </div>
            <Field
              label="Observations"
              error={observations.length > 2000 ? 'At most 2000 characters' : undefined}
            >
              <textarea
                value={observations}
                rows={4}
                maxLength={2000}
                onChange={(e) => {
                  setObservations(e.target.value)
                }}
              />
            </Field>
            <FormError message={save.error ? messageOf(save.error) : null} />
            <div className="actions">
              {listIsDraft && (
                <button
                  type="button"
                  className={line.is_active ? 'btn btn-danger' : 'btn'}
                  disabled={save.isPending}
                  onClick={() => {
                    save.mutate({ is_active: !line.is_active })
                  }}
                >
                  {line.is_active ? 'Exclude line' : 'Include line'}
                </button>
              )}
              <span className="spacer" />
              <button type="submit" className="btn btn-primary" disabled={save.isPending || tooLong}>
                Save
              </button>
            </div>
          </form>
        ) : (
          <dl className="kv kv-wide">
            <dt>Category</dt>
            <dd>{line.category ?? '—'}</dd>
            <dt>Brand</dt>
            <dd>{line.brand ?? '—'}</dd>
            <dt>Observations</dt>
            <dd className="wrap">{line.observations ?? '—'}</dd>
          </dl>
        )}
      </div>
    </Dialog>
  )
}
