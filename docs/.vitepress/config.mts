import { defineConfig } from 'vitepress'
import markdownItTaskCheckbox from 'markdown-it-task-checkbox'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  lang: 'zh-CN',
  title: "Vibe Trading",
  description: "AI驱动的多Agent协作加密货币量化交易系统",
  base: '/vibe-trading/',
  ignoreDeadLinks: [
    /localhost/,
    /CONTRIBUTING$/,
    /docker-compose\.yml$/
  ],
  markdown: {
    config: (md) => {
      md.use(markdownItTaskCheckbox)
    }
  },
  themeConfig: {
    // https://vitepress.dev/reference/default-theme-config
    logo: "/favicon.ico",
    nav: [
      { text: '快速开始', link: '/guide/quick-start' },
      { text: '系统架构', link: '/guide/architecture' },
      { text: 'Agent团队', link: '/guide/agents' }
    ],

    sidebar: [
      {
        text: '简介',
        items: [
          { text: '快速开始', link: '/guide/quick-start' },
          { text: '项目简介', link: '/guide/intro' },
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
      },
      {
        text: '开发指南',
        items: [
          { text: '参与贡献', link: '/develop/contributing' },
          { text: '开发路线图', link: '/develop/roadmap' },
          { text: '版本变更记录', link: '/develop/changelog' }
        ]
      }
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/encyc/vibe-trading' }
    ],

    footer: {
      message: '本项目基于 MIT License 开源，欢迎使用和贡献。',
      copyright: 'Copyright © 2026-present Vibe Trading'
    },

    editLink: {
      pattern: 'https://github.com/encyc/vibe-trading/edit/main/docs/:path',
      text: '在 GitHub 上编辑此页'
    },

    lastUpdated: {
      text: '最后更新时间',
      formatOptions: {
        dateStyle: 'full',
        timeStyle: 'medium'
      }
    },

    search: {
      provider: 'local'
    },

    docFooter: {
      prev: '上一页',
      next: '下一页'
    }
  },
})
