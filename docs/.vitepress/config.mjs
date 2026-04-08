// .vitepress/config.mjs
import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Vibe Trading',
  description: 'AI驱动的多Agent协作加密货币量化交易系统',
  
  // 部署到 GitHub Pages 需要配置 base
  // base: '/vibe-trading/',
  
  // 主题配置
  themeConfig: {
    // 导航栏
    nav: [
      { text: '快速开始', link: '/guide/quick-start' },
      { text: '项目简介', link: '/guide/intro' },
      { text: '系统架构', link: '/guide/architecture' },
      { text: 'Agent团队', link: '/guide/agents' },
      { text: 'Web监控', link: '/guide/monitoring' },
      { text: 'GitHub', link: 'https://github.com/encyc/vibe-trading' }
    ],

    // 侧边栏
    sidebar: {
      '/guide/': [
        {
          text: '入门指南',
          items: [
            { text: '快速开始', link: '/guide/quick-start' },
            { text: '项目简介', link: '/guide/intro' }
          ]
        },
        {
          text: '核心概念',
          items: [
            { text: '系统架构', link: '/guide/architecture' },
            { text: 'Agent团队', link: '/guide/agents' },
            { text: '协作流程', link: '/guide/workflow' }
          ]
        },
        {
          text: '使用指南',
          items: [
            { text: 'Web监控', link: '/guide/monitoring' },
            { text: '回测系统', link: '/guide/backtest' },
            { text: '配置说明', link: '/guide/configuration' }
          ]
        },
        {
          text: '进阶功能',
          items: [
            { text: '记忆系统', link: '/guide/memory' },
            { text: '自定义Agent', link: '/guide/custom-agent' },
            { text: 'API文档', link: '/guide/api' }
          ]
        }
      ]
    },

    // 社交链接
    socialLinks: [
      { icon: 'github', link: 'https://github.com/encyc/vibe-trading' }
    ],

    // 页脚
    footer: {
      message: '基于 MIT 许可证发布',
      copyright: 'Copyright © 2026 Vibe Trading'
    },

    // 搜索
    search: {
      provider: 'local'
    }
  },

  // Markdown 配置
  markdown: {
    lineNumbers: true
  },

  // 自定义样式
  head: [
    ['link', { rel: 'icon', href: '/favicon.ico' }]
  ]
})