// Client-side mirrors of the API's rules (app/parties/schemas.py). The API re-checks everything.
import { z } from 'zod'

const blankToNull = (v: string) => (v.trim() === '' ? null : v.trim())
const compactUpper = (v: string) => v.replace(/\s+/g, '').toUpperCase()

export const optionalText = (max: number) =>
  z.string().max(max, `At most ${String(max)} characters`).transform(blankToNull)

export const requiredText = (max: number, label = 'This field') =>
  z
    .string()
    .trim()
    .min(1, `${label} is required`)
    .max(max, `At most ${String(max)} characters`)

export const code = z
  .string()
  .transform(compactUpper)
  .pipe(z.string().regex(/^[A-Z0-9][A-Z0-9_-]{1,19}$/, '2–20 letters, digits, - or _'))

export const eori = z
  .string()
  .transform((v) => (v.trim() === '' ? null : compactUpper(v)))
  .pipe(
    z
      .string()
      .regex(/^[A-Z]{2}[A-Z0-9]{1,15}$/, 'Country code + up to 15 letters/digits, e.g. ESB12345678')
      .nullable(),
  )

export const isoCountry = z.string().regex(/^[A-Z]{2}$/, 'Choose a country')
export const isoCurrency = z.string().regex(/^[A-Z]{3}$/, 'Choose a currency')

export const email = z
  .string()
  .transform(blankToNull)
  .pipe(z.email({ message: 'Enter a valid email address' }).max(254).nullable())

export const phone = z
  .string()
  .transform(blankToNull)
  .pipe(
    z
      .string()
      .regex(/^[0-9+() ./x-]{3,40}$/, 'Digits, spaces and + ( ) . / - only')
      .nullable(),
  )
