// Safety: the e2e suite writes data through whatever stack is running on :8080. Refuse to
// run unless that stack is the e2e one (`make e2e`): its sign-in goes to the mock Google on
// :8090, and that API refuses to start unless its database ends in _e2e/_test. Against the
// normal stack (real Google, real `mdm` database) nothing runs.
export default async function globalSetup(): Promise<void> {
  const res = await fetch('http://localhost:8080/auth/login', { redirect: 'manual' })
  const target = res.headers.get('location') ?? ''
  const host = target ? new URL(target).origin : 'nowhere'
  if (!target.startsWith('http://localhost:8090/authorize')) {
    throw new Error(
      `Refusing to run the e2e suite: http://localhost:8080 is not the e2e stack (sign-in goes to ${host}). ` +
        'Run it with `make e2e`, which starts the stack with the mock Google and the mdm_e2e database.',
    )
  }
}
