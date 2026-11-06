import { api, query, type Page } from '../../api/client'

export type ListStatus = 'draft' | 'active' | 'expired'

export interface PriceList {
  id: string
  party_id: string
  name: string
  currency: string
  valid_from: string
  valid_to: string | null
  status: ListStatus
  effective_status: ListStatus
  revision: number
  supersedes_id: string | null
  source_file_name: string
  source_file_sha256: string
  source_sheet: string | null
  imported_at: string
  imported_by_email: string | null
  updated_at: string
  updated_by_email: string | null
  notes: string | null
  line_count: number
  version: number
}

export interface Facet {
  value: string | null
  count: number
}

export interface PriceListDetail extends PriceList {
  lines_with_warnings: number
  excluded_lines: number
  duplicate_groups: number
  brands: Facet[]
  categories: Facet[]
  price_columns: { price_type: string; currency: string; count: number }[]
}

export interface Price {
  price_type: string
  currency: string
  amount: string // decimal as text: never a float
}

export interface Line {
  id: string
  source_row: number
  ean: string | null
  upc: string | null
  asin: string | null
  vendor_sku: string | null
  description: string | null
  observations: string | null
  category: string | null
  brand: string | null
  case_pack_qty: number | null
  moq: number | null
  uom: string | null
  country_of_origin: string | null
  hs_code: string | null
  dimensions: Record<string, string | null> | null
  issues: string[]
  duplicate: boolean
  is_active: boolean
  version: number
  prices: Price[]
}

export interface LineParams {
  q?: string
  brand?: string
  category?: string
  only?: '' | 'duplicates' | 'warnings' | 'excluded'
  sort: string
  order: 'asc' | 'desc'
  page: number
  page_size: number
}

/** Filter value for "no category" / "no brand". */
export const NONE = '__none__'

export const listVersions = (partyId: string) => api<PriceList[]>(`/api/parties/${partyId}/price-lists`)
export const getPriceList = (id: string) => api<PriceListDetail>(`/api/price-lists/${id}`)
export const listLines = (id: string, p: LineParams) =>
  api<Page<Line>>(`/api/price-lists/${id}/lines${query({ ...p })}`)
export const updateLine = (
  line: Line,
  body: { category?: string | null; brand?: string | null; observations?: string | null; is_active?: boolean },
) =>
  api<Line>(`/api/price-list-lines/${line.id}`, {
    method: 'PATCH',
    body: JSON.stringify({ ...body, version: line.version }),
  })
export const activate = (pl: PriceList) =>
  api<PriceList>(`/api/price-lists/${pl.id}/activate`, {
    method: 'POST',
    body: JSON.stringify({ version: pl.version }),
  })
export const deleteDraft = (pl: PriceList) =>
  api<null>(`/api/price-lists/${pl.id}${query({ version: pl.version })}`, { method: 'DELETE' })

export const ISSUE_LABELS: Record<string, string> = {
  invalid_ean: 'Invalid EAN',
  invalid_upc: 'Invalid UPC',
  invalid_asin: 'Invalid ASIN',
  duplicate_key: 'Duplicate',
  missing_currency: 'Price without currency',
  invalid_currency: 'Unknown currency',
  invalid_amount: 'Price is not a number',
  negative_amount: 'Negative price',
  invalid_country: 'Unknown country of origin',
  invalid_case_pack_qty: 'Case pack not a whole number',
  invalid_moq: 'MOQ not a whole number',
  too_long: 'Text cut to length',
  no_product_key: 'No EAN, UPC or ASIN',
}

/** Money as text, with grouping, without ever turning it into a float. */
export function formatAmount(amount: string): string {
  const [int = '0', frac = ''] = amount.split('.')
  const neg = int.startsWith('-')
  const digits = neg ? int.slice(1) : int
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const cents = frac.replace(/0+$/, '').padEnd(2, '0')
  return `${neg ? '-' : ''}${grouped}.${cents}`
}
