#!/bin/bash
ollama serve &
SERVE_PID=$!
sleep 5
MODEL="${LLM_MODEL:-mistral}"
echo "Checking if model '$MODEL' is available..."
if ! ollama list | grep -q "$MODEL"; then
    echo "Pulling model '$MODEL'..."
    ollama pull "$MODEL"
    echo "Model '$MODEL' pulled successfully."
else
    echo "Model '$MODEL' already available."
fi
wait $SERVE_PID
