# 贡献指南（中文）

感谢你帮助改进《人生进阶指南》。欢迎提交能让事实更准确、任务更可执行、翻译更忠实，或让站点更容易、更安全使用的改动。

## 提交前

1. 使用 Node.js 24，并运行 `npm ci` 安装锁定版本的依赖。
2. 从最新 `main` 创建聚焦的分支，避免把无关格式或媒体文件混入同一个改动。
3. 修改导航、中文首页或中文词表后运行 `npm run sync`。
4. 提交前运行 `npm run check`、`npm run docs:build` 和 `npm run test:smoke`；如果没有运行某项，请在 PR 中说明原因。

## 内容标准

- 区分研究结论、个人经历和待验证假设；事实或产品主张优先使用一手来源并注明核验日期。
- 不把医疗、法律、财务、心理健康或安全内容写成专业建议。
- 每个公开中文页面都需要完整的英文对应页，保留任务、限制、证据等级和隐私边界。
- 新页面补充 `title`、`description` 和真实的 `updated: YYYY-MM-DD` frontmatter，并加入 `docs/.vitepress/navigation.mjs`。
- 图片使用能说明场景或用途的替代文本；不得提交隐私数据、秘密或未经授权的第三方素材。

## 选择入口

- 内容错误、过期资料或证据补充：使用 **Content error** issue form。
- 翻译缺失或中英文含义漂移：使用 **Translation issue** issue form。
- 学习方法建议或读者实践回执：使用对应的 **Learning-method proposal** 或 **Reader field note** form。
- 站点、无障碍或链接问题：使用 **Site or accessibility problem** 或 **Broken link** form。
- 安全和隐私问题：请按照 [SECURITY.md](SECURITY.md) 的私下流程处理，不要公开发布敏感信息。

## 许可

正文与作者内容采用 CC BY-NC 4.0，站点配置、检查脚本和构建代码采用 MIT；提交改动即表示你同意按照 [LICENSE.md](LICENSE.md) 中适用的许可发布，除非文件另有说明。

更完整的命令、隐私与媒体要求见英文版 [CONTRIBUTING.md](CONTRIBUTING.md)。
