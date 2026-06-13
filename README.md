# ⚽ 2026 FIFA World Cup 信息面板

全中文 · 动态倒计时 · AI预测 · 自动更新比分

[![自动更新比分](https://github.com/Cscaicai/2026-worldcup-dashboard/actions/workflows/update-scores.yml/badge.svg)](https://github.com/Cscaicai/2026-worldcup-dashboard/actions/workflows/update-scores.yml)

## 🌐 在线访问

https://cscaicai.github.io/2026-worldcup-dashboard/

## 🔄 自动更新

每4小时通过  **ESPN公开接口** 自动拉取最新比分，数据更新后自动部署到GitHub Pages。

- 定时：UTC 4:00 / 10:00 / 16:00 / 22:00（美东 0/6/12/18点）
- 零费用，零外部依赖
- 可手动触发：Actions → update-scores → Run workflow

## 📋 功能

- 104场比赛完整赛程（小组72 + 淘汰32）
- 12组48支球队中文名 + 国旗emoji
- 动态倒计时至决赛
- AI预测比分 + 可靠度
- 三色状态标识（已结束/未开始/直播中）
- 全中文界面 · 深色主题 · 响应式设计

## 📁 文件结构

```
├── index.html               # 主面板（单文件）
├── scripts/
│   └── update_scores.py     # 比分自动更新脚本
└── .github/workflows/
    └── update-scores.yml    # GitHub Actions定时工作流
```

## 📊 数据来源

比分数据来自 [ESPN Sports API](https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard)（免费公开接口）。
