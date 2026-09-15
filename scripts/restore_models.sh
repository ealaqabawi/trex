#!/bin/sh
# Re-download the local models T-REX uses for AI commentary.
# Removed to reclaim ~18GB; the signal card never needed them.
set -e
ollama pull llama3.2:1b
ollama pull qwen3:4b
ollama pull llama3.1:8b
ollama pull mistral:7b
ollama pull qwen2.5:7b
ollama pull llama3.2:latest
