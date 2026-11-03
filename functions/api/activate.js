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

  const code = (body.code || '').trim().toUpperCase();
  const deviceId = (body.deviceId || '').trim();
  if (!code || !deviceId) {
    return new Response(JSON.stringify({ ok: false, error: 'missing_params' }), { status: 400, headers: { ...cors, 'Content-Type': 'application/json' } });
  }

  // 1. 该设备是否已激活
  const devBind = await env.ACTIVATE_KV.get(`device:${deviceId}`, 'json');
  if (devBind) {
    return new Response(JSON.stringify({ ok: true, msg: 'already_activated', code: devBind.code }), { headers: { ...cors, 'Content-Type': 'application/json' } });
  }

  // 2. 密码是否存在
  const codeBind = await env.ACTIVATE_KV.get(`code:${code}`, 'json');
  if (!codeBind) {
    return new Response(JSON.stringify({ ok: false, error: 'invalid_code' }), { status: 403, headers: { ...cors, 'Content-Type': 'application/json' } });
  }

  // 3. 密码是否已被别的设备用过
  if (codeBind.deviceId && codeBind.deviceId !== deviceId) {
    return new Response(JSON.stringify({ ok: false, error: 'code_used' }), { status: 403, headers: { ...cors, 'Content-Type': 'application/json' } });
  }

  // 4. 绑定
  const now = new Date().toISOString();
  await env.ACTIVATE_KV.put(`code:${code}`, JSON.stringify({ deviceId, activatedAt: now }));
  await env.ACTIVATE_KV.put(`device:${deviceId}`, JSON.stringify({ code, activatedAt: now }));
  return new Response(JSON.stringify({ ok: true, msg: 'activated' }), { headers: { ...cors, 'Content-Type': 'application/json' } });
}
