import { auth } from '@clerk/nextjs/server';
import { App } from '@/components/app/app';

export default async function Page() {
  await auth.protect();

  return <App agentName={process.env.AGENT_NAME} />;
}
