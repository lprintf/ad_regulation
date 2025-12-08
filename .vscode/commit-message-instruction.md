请根据以下代码变更内容，生成一条简明扼要的 Git 提交摘要。
要求：
严格遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范；
默认使用英文小写，以 <type>(<scope>): <subject> 格式书写（scope 可选）；
type 从以下常见类型中选择：feat、fix、docs、style、refactor、test、build、ci、chore、perf；
<subject> 用祈使句，不超过 72 个字符，不加句号；重要subject用中文撰写。
不要包含解释、换行或多条信息，仅输出一行提交摘要。

✅ 示例输入（供参考）：
修改了 .gitignore 文件，添加 logs/ 和 *.tmp (添加字段表示 to exclude，删除字段表示 to include。)
✅ 模型应输出：
text
chore: update .gitignore to exclude logs and temp files

