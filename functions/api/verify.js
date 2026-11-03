export async function onRequestPost(context) {
  const { request, env } = context;
  const cors = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
  let body;
  try { body = await request.json(); } catch {
    return new Response(JSON.stringify({ ok: false, error: 'bad_request' }), { status: 400, headers: { ...cors, 'Content-Type': 'application/json' } });
  }
  const deviceId = (body.deviceId || '').trim();
  if (!deviceId) {
    return new Response(JSON.stringify({ ok: false, error: 'missing_params' }), { status: 400, headers: { ...cors, 'Content-Type': 'application/json' } });
  }
  const devBind = await env.ACTIVATE_KV.get(`device:${deviceId}`, 'json');
  return new Response(
    JSON.stringify({ ok: !!devBind, code: devBind?.code }),
    { headers: { ...cors, 'Content-Type': 'application/json' } }
  );
}
