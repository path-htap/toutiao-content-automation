/**
 * 飞书对话机器人 - Cloudflare Workers
 * 
 * 功能：
 * 1. 接收飞书消息事件（用户在群里 @机器人 或私聊）
 * 2. 解析用户指令（"生成文章""热点""重新生成"等）
 * 3. 触发 GitHub Actions 运行对应的流水线
 * 4. 回复用户"收到，正在处理"
 * 
 * 部署：
 * - 配置环境变量：GITHUB_TOKEN, GITHUB_REPO, FEISHU_APP_ID, FEISHU_APP_SECRET
 * - 飞书后台事件回调地址填 Worker 的 URL
 */

export default {
  async fetch(request, env) {
    if (request.method === 'GET') {
      return new Response('✅ 飞书对话机器人运行中', { status: 200 });
    }

    if (request.method === 'POST') {
      try {
        const body = await request.json();
        
        // 飞书 URL 验证（首次配置回调时会发 challenge）
        if (body.type === 'url_verification') {
          return new Response(JSON.stringify({ challenge: body.challenge }), {
            headers: { 'Content-Type': 'application/json' },
          });
        }

        // 处理飞书事件
        if (body.header?.event_type === 'im.message.receive_v1') {
          await handleMessage(body.event, env);
          return new Response('ok', { status: 200 });
        }

        return new Response('ok', { status: 200 });
      } catch (e) {
        console.error('处理失败:', e);
        return new Response('error', { status: 500 });
      }
    }

    return new Response('Method Not Allowed', { status: 405 });
  },
};

async function handleMessage(event, env) {
  const message = event.message;
  const sender = event.sender;
  const chatType = message.chat_type; // group / p2p

  // 只处理文本消息
  if (message.message_type !== 'text') {
    return;
  }

  let content;
  try {
    content = JSON.parse(message.content).text || '';
  } catch {
    return;
  }

  // 群消息需要 @ 机器人才响应
  if (chatType === 'group') {
    // 去掉 @机器人 的部分
    content = content.replace(/@_user_\d+/g, '').trim();
    if (!content) {
      // 只 @ 没说话，回复一个帮助
      await replyMessage(message.message_id, `📋 我可以帮你做这些：

**生成文章** - 抓取热点并生成文章
**看热点** - 只抓取今日热点
**重新生成** - 重新跑一遍
**帮助** - 查看帮助

直接对我说就行～`, env);
      return;
    }
  }

  // 解析指令
  const command = parseCommand(content);
  
  if (command.type === 'help') {
    await replyMessage(message.message_id, `📋 我可以帮你做这些：

**生成文章** - 抓取热点并生成完整文章（配图+去AI味）
**看热点** - 只抓取今日热点，不生成文章
**重新生成** - 重新完整跑一遍流水线
**帮助** - 查看帮助

直接对我说就行～`, env);
    return;
  }

  // 触发 GitHub Actions
  await triggerGitHubAction(command, env);

  // 回复用户
  const replyText = getReplyText(command);
  await replyMessage(message.message_id, replyText, env);
}

function parseCommand(text) {
  const t = text.toLowerCase().trim();

  if (t.includes('帮助') || t.includes('help') || t.includes('怎么用') || t.includes('干啥')) {
    return { type: 'help' };
  }

  if (t.includes('热点') || t.includes('热搜') || t.includes('有啥')) {
    return { type: 'hot_topics', phase: '2' };
  }

  if (t.includes('重新生成') || t.includes('再来') || t.includes('重新跑') || t.includes('重新来')) {
    return { type: 'regenerate', phase: 'all' };
  }

  if (t.includes('生成') || t.includes('写文章') || t.includes('写') || t.includes('文章') || t.includes('全部') || t.includes('完整')) {
    return { type: 'full_run', phase: 'all' };
  }

  // 默认：完整运行
  return { type: 'full_run', phase: 'all' };
}

function getReplyText(command) {
  switch (command.type) {
    case 'hot_topics':
      return '🔍 收到！正在抓取今日热点，稍等几分钟～';
    case 'regenerate':
      return '🔄 收到！重新生成中，大概 5-10 分钟搞定～';
    case 'full_run':
    default:
      return '✍️ 收到！正在生成文章，大概 5-10 分钟后发过来～';
  }
}

async function triggerGitHubAction(command, env) {
  const token = env.GITHUB_TOKEN;
  const repo = env.GITHUB_REPO; // 格式: owner/repo

  if (!token || !repo) {
    console.error('缺少 GITHUB_TOKEN 或 GITHUB_REPO 配置');
    return;
  }

  const url = `https://api.github.com/repos/${repo}/actions/workflows/daily.yml/dispatches`;

  const inputs = {
    phase: command.phase || 'all',
    command: command.type || 'full_run',
  };

  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': `token ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        ref: 'main',
        inputs: inputs,
      }),
    });

    if (resp.status === 204) {
      console.log('GitHub Actions 触发成功');
    } else {
      const text = await resp.text();
      console.error('GitHub Actions 触发失败:', resp.status, text);
    }
  } catch (e) {
    console.error('触发 GitHub Actions 异常:', e);
  }
}

async function replyMessage(messageId, text, env) {
  // 获取 tenant_access_token
  const token = await getTenantToken(env);
  if (!token) return;

  try {
    const resp = await fetch('https://open.feishu.cn/open-apis/im/v1/messages/reply', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message_id: messageId,
        msg_type: 'text',
        content: JSON.stringify({ text: text }),
      }),
    });

    const data = await resp.json();
    if (data.code !== 0) {
      console.error('回复消息失败:', data);
    }
  } catch (e) {
    console.error('回复消息异常:', e);
  }
}

let cachedToken = null;
let tokenExpireTime = 0;

async function getTenantToken(env) {
  const now = Date.now() / 1000;
  if (cachedToken && now < tokenExpireTime - 60) {
    return cachedToken;
  }

  try {
    const resp = await fetch('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        app_id: env.FEISHU_APP_ID,
        app_secret: env.FEISHU_APP_SECRET,
      }),
    });

    const data = await resp.json();
    if (data.code === 0) {
      cachedToken = data.tenant_access_token;
      tokenExpireTime = now + data.expire;
      return cachedToken;
    }
    console.error('获取 tenant_access_token 失败:', data);
    return null;
  } catch (e) {
    console.error('获取 tenant_access_token 异常:', e);
    return null;
  }
}
