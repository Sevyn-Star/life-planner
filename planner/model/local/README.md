# 本地小模型

权重放在项目里的 `models/`，文件是 `qwen2.5-0.5b-instruct-q4_k_m.gguf`，491 MB。不提交，也不放进 `rensheng/`。

书没筛中时，页面和命令行直接读这份权重，用自己的话写一段模型自述。这一步不另开服务。

筛中之后若要改写最小动作，程序仍只确认 `PLANNER_LOCAL_WEIGHTS` 指向 `models/` 里一块已经存在的路径，然后把和 API 相同的输入包发给本机服务。它不把权重内容放进那份输入包。

本机服务要事先启动，并使用那份权重。接口需要兼容 OpenAI 的 `chat/completions`，例如 llama.cpp 的 server，或 Ollama 的兼容地址。

```bash
export PLANNER_MODEL=local
export PLANNER_LOCAL_WEIGHTS=models/qwen2.5-0.5b-instruct-q4_k_m.gguf
export PLANNER_LOCAL_URL=http://127.0.0.1:8080/v1
export PLANNER_LOCAL_MODEL=服务里的模型名
python3 -m planner.cli --context data/context/sample-open.md "我不知道从哪开始，只想重新动一下。今天有半小时。"
```

`PLANNER_MODEL=local` 时不再走 API。密钥不要写进这个目录。
