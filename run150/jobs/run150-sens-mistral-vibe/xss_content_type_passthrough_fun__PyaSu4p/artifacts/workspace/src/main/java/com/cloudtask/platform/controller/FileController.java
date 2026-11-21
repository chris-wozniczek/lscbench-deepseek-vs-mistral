package com.cloudtask.platform.controller;

import com.cloudtask.platform.dto.ApiResponse;
import com.cloudtask.platform.entity.FileRecord;
import com.cloudtask.platform.entity.Workspace;
import com.cloudtask.platform.service.FileService;
import com.cloudtask.platform.service.WorkspaceService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

@RestController
@RequestMapping("/api/files")
public class FileController {

    private final FileService fileService;
    private final WorkspaceService workspaceService;

    public FileController(FileService fileService, WorkspaceService workspaceService) {
        this.fileService = fileService;
        this.workspaceService = workspaceService;
    }

    @GetMapping("/{id}")
    public void download(@PathVariable Long id, HttpServletRequest request, HttpServletResponse response) throws IOException {
        Long userId = (Long) request.getAttribute("userId");
        String role = (String) request.getAttribute("role");

        FileRecord record = fileService.getFileById(id);
        if (record == null) {
            writeJsonError(response, 404, "{\"code\":404,\"message\":\"文件不存在\",\"data\":null}");
            return;
        }

        Workspace ws = workspaceService.getWorkspaceById(record.getWorkspaceId());
        if (!"ADMIN".equals(role) && !ws.getUserId().equals(userId)) {
            writeJsonError(response, 403, "{\"code\":403,\"message\":\"权限不足\",\"data\":null}");
            return;
        }

        String encodedName = URLEncoder.encode(record.getOriginalName(), StandardCharsets.UTF_8).replace("+", "%20");
        response.setContentType(record.getContentType());
        response.setHeader("Content-Disposition", "attachment; filename=\"" + encodedName + "\"; filename*=UTF-8''" + encodedName);
        response.setContentLengthLong(record.getFileSize());
        response.getOutputStream().write(record.getFileData());
        response.getOutputStream().flush();
    }

    private void writeJsonError(HttpServletResponse response, int status, String body) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        response.setContentLength(bytes.length);
        response.getOutputStream().write(bytes);
        response.getOutputStream().flush();
    }

    @GetMapping("/{id}/info")
    public ResponseEntity<ApiResponse<?>> info(@PathVariable Long id, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        String role = (String) request.getAttribute("role");

        FileRecord file = fileService.getFileById(id);
        if (file == null) {
            return ResponseEntity.status(404).body(ApiResponse.error(404, "文件不存在"));
        }

        Workspace ws = workspaceService.getWorkspaceById(file.getWorkspaceId());
        if (!"ADMIN".equals(role) && !ws.getUserId().equals(userId)) {
            return ResponseEntity.status(403).body(ApiResponse.error(403, "权限不足"));
        }

        return ResponseEntity.ok(fileService.getFileInfo(id));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<?>> delete(@PathVariable Long id, HttpServletRequest request) {
        Long userId = (Long) request.getAttribute("userId");
        String role = (String) request.getAttribute("role");

        FileRecord file = fileService.getFileById(id);
        if (file == null) {
            return ResponseEntity.status(404).body(ApiResponse.error(404, "文件不存在"));
        }

        Workspace ws = workspaceService.getWorkspaceById(file.getWorkspaceId());
        if (!"ADMIN".equals(role) && !ws.getUserId().equals(userId)) {
            return ResponseEntity.status(403).body(ApiResponse.error(403, "权限不足"));
        }

        return ResponseEntity.ok(fileService.deleteFile(id));
    }
}
