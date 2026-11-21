package com.mediaflow.platform.service;

import com.mediaflow.platform.entity.Task;
import com.mediaflow.platform.entity.Template;
import com.mediaflow.platform.mapper.TaskMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Service
public class MediaProcessService {

    @Autowired
    private TaskMapper taskMapper;

    public void processVideo(Task task, Template template) {
        Thread worker = new Thread(() -> runProcess(task, template), "media-process");
        worker.start();
    }

    private void runProcess(Task task, Template template) {
        try {
            List<String> command = new ArrayList<>();
            command.add("ffmpeg");
            command.add("-y");
            command.add("-i");
            command.add("/data/input/" + task.getInputFile());
            command.add("-c:v");
            command.add(template.getCodec());
            command.add("-b:v");
            command.add(template.getBitrate());
            command.add("-s");
            command.add(template.getResolution());

            String watermarkContent = task.getWatermarkContent();
            if (watermarkContent != null && !watermarkContent.isEmpty()) {
                command.add("-vf");
                command.add(buildWatermarkFilter(watermarkContent,
                        task.getWatermarkFontSize(), task.getWatermarkPosition()));
            }

            command.add(task.getOutputFile());

            ProcessBuilder processBuilder = new ProcessBuilder(command);
            processBuilder.redirectErrorStream(true);
            processBuilder.redirectOutput(ProcessBuilder.Redirect.DISCARD);
            Process process = processBuilder.start();
            int exitCode = process.waitFor();

            if (exitCode == 0) {
                taskMapper.updateStatus(task.getId(), "COMPLETED", task.getOutputFile(), null, LocalDateTime.now());
            } else {
                markFailed(task, "ffmpeg exited with code " + exitCode);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            markFailed(task, "Processing interrupted: " + describe(e));
        } catch (Exception e) {
            markFailed(task, "Processing failed: " + describe(e));
        }
    }

    private void markFailed(Task task, String message) {
        String errorMessage = message.length() > 1000 ? message.substring(0, 1000) : message;
        try {
            taskMapper.updateStatus(task.getId(), "FAILED", task.getOutputFile(), errorMessage, LocalDateTime.now());
        } catch (Exception ignored) {
            // Nothing further can be reported once persistence itself fails.
        }
    }

    private String describe(Exception e) {
        String message = e.getMessage();
        return message != null && !message.isEmpty() ? message : e.getClass().getName();
    }

    private String buildWatermarkFilter(String content, Integer fontSize, String position) {
        int size = fontSize != null ? fontSize : 24;
        String escaped = content
                .replace("\\", "\\\\")
                .replace("'", "\\'")
                .replace(":", "\\:")
                .replace("%", "\\%");
        String x;
        String y;
        String corner = position != null ? position : "top-left";
        switch (corner) {
            case "top-right":
                x = "w-tw-10";
                y = "10";
                break;
            case "bottom-left":
                x = "10";
                y = "h-th-10";
                break;
            case "bottom-right":
                x = "w-tw-10";
                y = "h-th-10";
                break;
            case "top-left":
            default:
                x = "10";
                y = "10";
                break;
        }
        return "drawtext=text='" + escaped + "':fontsize=" + size + ":fontcolor=white:x=" + x + ":y=" + y;
    }
}
