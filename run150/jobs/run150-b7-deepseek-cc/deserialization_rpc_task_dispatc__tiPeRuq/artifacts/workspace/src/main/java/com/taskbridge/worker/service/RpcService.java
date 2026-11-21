package com.taskbridge.worker.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.taskbridge.worker.dto.ApiResponse;
import com.taskbridge.worker.dto.BatchDispatchRequest;
import com.taskbridge.worker.dto.DispatchRequest;
import com.taskbridge.worker.entity.TaskExecution;
import com.taskbridge.worker.entity.TaskType;
import com.taskbridge.worker.mapper.TaskExecutionMapper;
import com.taskbridge.worker.mapper.TaskTypeMapper;
import org.springframework.stereotype.Service;

import java.io.*;
import java.time.LocalDateTime;
import java.util.*;

@Service
public class RpcService {

    private static final java.time.format.DateTimeFormatter TIMESTAMP_FORMAT =
            java.time.format.DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    private final TaskTypeMapper taskTypeMapper;
    private final TaskExecutionMapper taskExecutionMapper;
    private final ObjectMapper objectMapper;

    public RpcService(TaskTypeMapper taskTypeMapper, TaskExecutionMapper taskExecutionMapper, ObjectMapper objectMapper) {
        this.taskTypeMapper = taskTypeMapper;
        this.taskExecutionMapper = taskExecutionMapper;
        this.objectMapper = objectMapper;
    }

    public ApiResponse<?> dispatch(DispatchRequest request) {
        TaskType taskType = taskTypeMapper.findByName(request.getTaskTypeName());
        if (taskType == null) {
            return ApiResponse.error(404, "任务类型不存在");
        }

        String encoding = request.getParamEncoding();
        if (encoding == null || encoding.isEmpty()) {
            encoding = taskType.getParamEncoding();
        }

        Object param;
        try {
            param = reconstruct(request.getParamData(), encoding);
        } catch (Exception e) {
            return ApiResponse.error(400, "参数反序列化失败");
        }

        String paramClass = param.getClass().getName();
        String result = "执行完成: " + simpleName(taskType.getHandlerClass()) + " processed";
        LocalDateTime submittedAt = LocalDateTime.now();

        TaskExecution execution = new TaskExecution();
        execution.setTaskTypeId(taskType.getId());
        execution.setExecutionId(request.getExecutionId());
        execution.setParamEncoding(encoding);
        execution.setParamClass(paramClass);
        execution.setParamPayload(request.getParamData());
        execution.setStatus("RUNNING");
        execution.setSubmittedAt(submittedAt);
        taskExecutionMapper.insert(execution);

        execution.setStatus("SUCCESS");
        execution.setResult(result);
        execution.setCompletedAt(LocalDateTime.now());
        taskExecutionMapper.update(execution);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("executionId", request.getExecutionId());
        data.put("taskTypeName", request.getTaskTypeName());
        data.put("paramEncoding", encoding);
        data.put("paramClass", paramClass);
        data.put("status", "SUCCESS");
        data.put("result", result);
        data.put("submittedAt", formatTimestamp(submittedAt));
        return ApiResponse.success("任务已提交", data);
    }

    public ApiResponse<?> dispatchBatch(BatchDispatchRequest request) {
        List<DispatchRequest> tasks = request.getTasks() != null ? request.getTasks() : Collections.emptyList();
        List<Map<String, Object>> results = new ArrayList<>();
        int success = 0;
        int failed = 0;

        for (DispatchRequest task : tasks) {
            ApiResponse<?> response = dispatch(task);
            boolean ok = response.getCode() == 200;
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("executionId", task.getExecutionId());
            item.put("status", ok ? "SUCCESS" : "FAILED");
            results.add(item);
            if (ok) {
                success++;
            } else {
                failed++;
            }
        }

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("total", tasks.size());
        data.put("success", success);
        data.put("failed", failed);
        data.put("results", results);
        return ApiResponse.success("批量提交完成", data);
    }

    public ApiResponse<?> retry(String executionId) {
        TaskExecution execution = taskExecutionMapper.findByExecutionId(executionId);
        if (execution == null) {
            return ApiResponse.error(404, "执行记录不存在");
        }

        TaskType taskType = taskTypeMapper.findById(execution.getTaskTypeId());
        if (taskType == null) {
            return ApiResponse.error(404, "任务类型不存在");
        }

        String encoding = execution.getParamEncoding();
        if (encoding == null || encoding.isEmpty()) {
            encoding = taskType.getParamEncoding();
        }

        Object param;
        try {
            param = reconstruct(execution.getParamPayload(), encoding);
        } catch (Exception e) {
            return ApiResponse.error(400, "参数反序列化失败");
        }

        String result = "重试完成: " + simpleName(taskType.getHandlerClass()) + " processed";
        execution.setParamClass(param.getClass().getName());
        execution.setStatus("SUCCESS");
        execution.setResult(result);
        execution.setCompletedAt(LocalDateTime.now());
        taskExecutionMapper.update(execution);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("executionId", executionId);
        data.put("status", "SUCCESS");
        data.put("result", result);
        return ApiResponse.success("重试完成", data);
    }

    public ApiResponse<?> listExecutions() {
        List<TaskExecution> executions = taskExecutionMapper.findAll();
        List<Map<String, Object>> items = new ArrayList<>();
        for (TaskExecution execution : executions) {
            items.add(toItem(execution, false));
        }
        return ApiResponse.success(items);
    }

    public ApiResponse<?> getExecution(String executionId) {
        TaskExecution execution = taskExecutionMapper.findByExecutionId(executionId);
        if (execution == null) {
            return ApiResponse.error(404, "执行记录不存在");
        }
        return ApiResponse.success(toItem(execution, true));
    }

    private Map<String, Object> toItem(TaskExecution execution, boolean includePayload) {
        TaskType taskType = execution.getTaskTypeId() == null
                ? null
                : taskTypeMapper.findById(execution.getTaskTypeId());

        Map<String, Object> item = new LinkedHashMap<>();
        item.put("id", execution.getId());
        item.put("executionId", execution.getExecutionId());
        item.put("taskTypeName", taskType == null ? null : taskType.getName());
        item.put("paramEncoding", execution.getParamEncoding());
        item.put("paramClass", execution.getParamClass());
        item.put("status", execution.getStatus());
        item.put("result", execution.getResult());
        item.put("submittedAt", formatTimestamp(execution.getSubmittedAt()));
        item.put("completedAt", formatTimestamp(execution.getCompletedAt()));
        if (includePayload) {
            item.put("paramPayload", execution.getParamPayload());
        }
        return item;
    }

    private String formatTimestamp(LocalDateTime timestamp) {
        return timestamp == null ? null : TIMESTAMP_FORMAT.format(timestamp);
    }

    private Object reconstruct(String paramData, String encoding) throws Exception {
        byte[] bytes = decodeBase64(paramData);
        if (encoding != null && "JAVA_OBJECT".equalsIgnoreCase(encoding)) {
            try (ObjectInputStream input = new ObjectInputStream(new ByteArrayInputStream(bytes))) {
                Object value = input.readObject();
                if (value == null) {
                    throw new IllegalArgumentException("null payload");
                }
                return value;
            }
        }
        Object value = objectMapper.readValue(bytes, Object.class);
        if (value == null) {
            throw new IllegalArgumentException("null payload");
        }
        return value;
    }

    private byte[] decodeBase64(String paramData) {
        try {
            return Base64.getDecoder().decode(paramData);
        } catch (IllegalArgumentException standardFailure) {
            try {
                return Base64.getUrlDecoder().decode(paramData);
            } catch (IllegalArgumentException urlSafeFailure) {
                return Base64.getMimeDecoder().decode(paramData);
            }
        }
    }

    private String simpleName(String handlerClass) {
        if (handlerClass == null) {
            return "Unknown";
        }
        int lastDot = handlerClass.lastIndexOf('.');
        return lastDot >= 0 ? handlerClass.substring(lastDot + 1) : handlerClass;
    }
}