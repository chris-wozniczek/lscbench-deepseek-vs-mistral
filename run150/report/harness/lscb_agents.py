import asyncio
import shlex
from pathlib import PurePosixPath

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.vibe import Vibe
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class VibeNoPluginCache(Vibe):
    def build_cli_flags(self) -> str:
        flags = super().build_cli_flags()
        export_dir = shlex.quote((self.environment_logs_dir / "vibe-export").as_posix())
        return f"{flags} --output-dir {export_dir}".strip()

    async def _remove_plugin_cache(self, environment: BaseEnvironment) -> None:
        plugin_cache = PurePosixPath(self._vibe_home) / "logs/session/plugins"
        command = f"rm -rf {shlex.quote(plugin_cache.as_posix())}"
        try:
            result = await environment.exec(command, timeout_sec=8)
            if result.return_code != 0:
                output = result.stderr or result.stdout or "no output"
                self.logger.warning(
                    "Failed to remove Vibe plugin cache with code %s: %s",
                    result.return_code,
                    output,
                )
        except asyncio.CancelledError:
            self.logger.warning("Vibe plugin-cache cleanup was cancelled")
        except Exception as exc:
            self.logger.warning("Failed to remove Vibe plugin cache: %s", exc)

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        try:
            export_dir = self.environment_logs_dir / "vibe-export"
            await self.exec_as_agent(
                environment,
                command=f"mkdir -p {shlex.quote(export_dir.as_posix())}",
            )
            await super().run(instruction, environment, context)
        finally:
            cleanup = asyncio.create_task(self._remove_plugin_cache(environment))
            try:
                await asyncio.wait_for(asyncio.shield(cleanup), timeout=10)
            except asyncio.CancelledError:
                try:
                    await asyncio.wait_for(asyncio.shield(cleanup), timeout=10)
                except Exception as exc:
                    self.logger.warning(
                        "Vibe plugin-cache cleanup did not finish after cancellation: %s",
                        exc,
                    )
                raise
            except Exception as exc:
                self.logger.warning("Vibe plugin-cache cleanup did not finish: %s", exc)


class ClaudeCodeFallbackInstall(ClaudeCode):
    async def install(self, environment: BaseEnvironment) -> None:
        try:
            await super().install(environment)
        except Exception as exc:
            lines = [line.strip() for line in str(exc).splitlines() if line.strip()]
            summary = f"{type(exc).__name__}: {lines[0] if lines else 'install failed'}"
            apt_error = next(
                (line for line in reversed(lines) if line.startswith("E: ")), None
            )
            if apt_error and apt_error not in summary:
                summary = f"{summary}; {apt_error}"
            self.logger.warning(
                "Claude Code installation failed; retrying with bootstrap fallback: %s",
                summary,
            )
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            (self.logs_dir / "install_fallback.txt").write_text(f"{summary}\n")
            await self.ensure_system_dependencies(environment, ("curl", "bash"))
            version_flag = f" {self._version}" if self._version else ""
            await self.exec_as_agent(
                environment,
                command=(
                    "set -euo pipefail; "
                    "curl -fsSL "
                    "https://downloads.claude.ai/claude-code-releases/bootstrap.sh "
                    f"| bash -s --{version_flag}; "
                    "echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc && "
                    'export PATH="$HOME/.local/bin:$PATH" && '
                    "claude --version"
                ),
            )


class VibePromptFile(VibeNoPluginCache):
    """Same as VibeNoPluginCache, but Vibe reads the instruction from a file.

    Harbor's Vibe adapter passes the instruction as `--prompt=<text>`, so it is
    visible in Vibe's process command line and `pkill -f <pattern>` run by the
    model can match and kill Vibe itself. `--prompt-file` keeps it out of argv.
    """

    _PROMPT_FILE = "/logs/agent/prompt.txt"

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        import base64

        encoded = base64.b64encode(instruction.encode()).decode()
        await self.exec_as_agent(
            environment,
            command=f"mkdir -p /logs/agent && echo {encoded} | base64 -d > {self._PROMPT_FILE}",
        )
        original_exec = self.exec_as_agent
        inline = f"--prompt={shlex.quote(instruction)} "

        async def exec_with_prompt_file(environment_, command, **kwargs):
            if inline in command:
                command = command.replace(inline, f"--prompt-file {self._PROMPT_FILE} ")
            return await original_exec(environment_, command=command, **kwargs)

        self.exec_as_agent = exec_with_prompt_file
        try:
            await super().run(instruction, environment, context)
        finally:
            self.exec_as_agent = original_exec
