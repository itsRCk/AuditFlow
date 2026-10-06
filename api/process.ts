import { QueueClient } from '@vercel/queue';

const queue = new QueueClient();

export default queue.handleNodeCallback<{ case_id: string }>(async (message) => {
  if (!/^[a-f0-9]{32}$/.test(message.case_id)) throw new Error('Invalid job identifier.');
  const origin = process.env.AUDITFLOW_PROCESSOR_URL;
  const token = process.env.AUDITFLOW_JOB_TOKEN;
  if (!origin || !token) throw new Error('Document processor is not configured.');
  const response = await fetch(new URL(`/api/internal/jobs/${message.case_id}`, origin), {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(280_000),
  });
  if (!response.ok) throw new Error('Document processing has not completed; retry the job.');
});
