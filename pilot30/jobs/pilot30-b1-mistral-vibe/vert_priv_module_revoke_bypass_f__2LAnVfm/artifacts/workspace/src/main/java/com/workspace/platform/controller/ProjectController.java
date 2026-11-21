package com.workspace.platform.controller;

import com.workspace.platform.dto.ApiResponse;
import com.workspace.platform.entity.Project;
import com.workspace.platform.service.ModuleAccessService;
import com.workspace.platform.service.ProjectService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/projects")
public class ProjectController {

    private final ProjectService projectService;
    private final ModuleAccessService moduleAccessService;

    public ProjectController(ProjectService projectService, ModuleAccessService moduleAccessService) {
        this.projectService = projectService;
        this.moduleAccessService = moduleAccessService;
    }

<MASKED>

<MASKED>

<MASKED>

<MASKED>
}