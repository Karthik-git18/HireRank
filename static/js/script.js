document.addEventListener("DOMContentLoaded", () => {
  const menuToggle = document.getElementById("menuToggle");
  const sidebar = document.getElementById("sidebar");
  menuToggle?.addEventListener("click", () => sidebar?.classList.toggle("sidebar-open"));

  document.querySelectorAll(".flash-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".flash")?.remove());
  });

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const fileInput = document.getElementById("resumeFiles");
  const fileSummary = document.getElementById("fileSummary");
  const dropzone = document.querySelector(".dropzone");
  const updateFileSummary = () => {
    const files = Array.from(fileInput.files || []);
    fileSummary.textContent = files.length
      ? `${files.length} PDF${files.length === 1 ? "" : "s"} selected`
      : "No files selected";
  };
  fileInput?.addEventListener("change", updateFileSummary);
  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("dropzone-active");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    dropzone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dropzone-active");
    });
  });
  dropzone?.addEventListener("drop", (event) => {
    const droppedFiles = event.dataTransfer?.files;
    if (!droppedFiles?.length || !fileInput) return;
    fileInput.files = droppedFiles;
    updateFileSummary();
  });

  const csrfToken = document.querySelector(
    '#candidateValidationForm input[name="csrf_token"], #interviewForm input[name="csrf_token"]',
  )?.value || "";
  const fetchJson = async (url, options = {}) => {
    const { timeoutMs = 20_000, ...fetchOptions } = options;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
        headers: {
          ...(fetchOptions.body ? { "Content-Type": "application/json" } : {}),
          ...(fetchOptions.method === "POST" ? { "X-CSRFToken": csrfToken } : {}),
          ...fetchOptions.headers,
        },
      });
      const responseText = await response.text();
      let data;
      try {
        data = responseText ? JSON.parse(responseText) : {};
      } catch {
        if (response.redirected) {
          throw new Error("Your session may have expired. Reload the page and sign in again.");
        }
        throw new Error(`The server returned an unexpected response (HTTP ${response.status}).`);
      }
      if (!response.ok) {
        throw new Error(
          typeof data?.error === "string" ? data.error : "The request could not be completed.",
        );
      }
      return data;
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new Error(`The request timed out after ${Math.round(timeoutMs / 1000)} seconds. Please try again.`);
      }
      throw error instanceof Error ? error : new Error("The network request could not be completed.");
    } finally {
      window.clearTimeout(timeoutId);
    }
  };

  const validationButton = document.getElementById("validateCandidate");
  if (validationButton) {
    const validationPanel = document.getElementById("validationPanel");
    const validationContent = document.getElementById("validationReportContent");
    const validationFeedback = document.getElementById("validationFeedback");
    const initialReport = document.getElementById("initialValidationReport");
    const validationCsrf = document.querySelector(
      '#candidateValidationForm input[name="csrf_token"]',
    )?.value || "";
    const originalButton = validationButton.innerHTML;

    const showValidationFeedback = (message, kind = "info") => {
      validationFeedback.textContent = message;
      validationFeedback.className = `validation-feedback feedback-${kind}`;
      validationFeedback.hidden = !message;
    };

    const textNode = (tag, className, value) => {
      const node = document.createElement(tag);
      if (className) node.className = className;
      node.textContent = value === null || value === undefined || value === ""
        ? "Not available"
        : String(value);
      return node;
    };

    const addReportSection = (container, title) => {
      const section = document.createElement("section");
      section.className = "validation-section";
      section.append(textNode("h3", "", title));
      container.append(section);
      return section;
    };

    const normalizeEvidence = (entries, defaultSource) => (entries || []).map((entry) => (
      typeof entry === "string"
        ? { source: defaultSource, sentence: entry }
        : { source: entry.source || defaultSource, sentence: entry.sentence }
    )).filter((entry) => entry.sentence);

    const addEvidenceDetails = (container, groups, summary = "View Evidence") => {
      const details = document.createElement("details");
      details.className = "validation-details";
      details.append(textNode("summary", "", summary));
      const content = document.createElement("div");
      content.className = "validation-detail-content";
      let found = false;
      groups.forEach(([label, entries]) => {
        const evidence = normalizeEvidence(entries, label);
        if (!evidence.length) return;
        found = true;
        content.append(textNode("strong", "validation-evidence-label", label));
        const list = document.createElement("ul");
        list.className = "validation-evidence";
        evidence.forEach((entry) => {
          const item = document.createElement("li");
          item.append(textNode("span", "validation-evidence-source", `${entry.source}: `));
          item.append(textNode("span", "", entry.sentence));
          list.append(item);
        });
        content.append(list);
      });
      if (!found) {
        content.append(textNode("span", "validation-empty", "No supporting resume sentence was found."));
      }
      details.append(content);
      container.append(details);
    };

    const appendHighlightedDescription = (container, description, evidenceSentences) => {
      const text = String(description || "");
      const ranges = (evidenceSentences || [])
        .map((sentence) => ({ sentence, start: text.indexOf(sentence) }))
        .filter((match) => match.start >= 0)
        .sort((first, second) => first.start - second.start);
      let cursor = 0;
      ranges.forEach(({ sentence, start }) => {
        if (start < cursor) return;
        container.append(document.createTextNode(text.slice(cursor, start)));
        const highlight = document.createElement("mark");
        highlight.className = "validation-evidence-highlight";
        highlight.textContent = sentence;
        container.append(highlight);
        cursor = start + sentence.length;
      });
      container.append(document.createTextNode(text.slice(cursor)));
    };

    const renderValidationReport = (report) => {
      if (!report || typeof report !== "object" || !report.overview) {
        throw new Error("The validation report is incomplete. Please try again.");
      }
      validationContent.replaceChildren();
      const generated = textNode(
        "p",
        "muted validation-generated",
        report.generated_at ? `Generated ${new Date(report.generated_at).toLocaleString()}` : "",
      );
      validationContent.append(generated);
      if (report.validation_status) {
        const statusSection = addReportSection(validationContent, "Review status");
        const status = String(report.validation_status);
        const badgeClass = status === "Passed"
          ? "badge-success"
          : status === "Warning" ? "badge-rejected" : "badge-warning";
        const badge = textNode("span", `badge ${badgeClass}`, status);
        statusSection.append(badge);
        statusSection.append(textNode(
          "p",
          "muted validation-section-note",
          "Decision-support checks only. Review the source resume; no status automatically rejects a candidate.",
        ));
        if (report.findings?.length) {
          const findings = document.createElement("ul");
          findings.className = "validation-quality-list";
          report.findings.forEach((finding) => {
            const item = document.createElement("li");
            item.append(textNode("strong", "", `${finding.status}: ${finding.message} `));
            item.append(textNode("span", "", finding.evidence));
            findings.append(item);
          });
          statusSection.append(findings);
        }
      }

      const requiredSkills = (report.skills || []).filter((item) => item.requirement === "Required");
      const overview = report.overview;
      const counts = [
        ["Required Skills", overview.total_required_skills ?? requiredSkills.length],
        ["Skills Identified", overview.skills_identified ?? requiredSkills.filter((item) => item.status !== "Evidence not found").length],
        ["Skills With Evidence", overview.skills_with_evidence ?? requiredSkills.filter((item) => item.status === "Evidence found").length],
        ["Skills Requiring Review", overview.skills_requiring_review ?? requiredSkills.filter((item) => item.status !== "Evidence found").length],
      ];
      const summary = addReportSection(validationContent, "Validation overview");
      const stats = document.createElement("div");
      stats.className = "validation-stats";
      counts.forEach(([label, count]) => {
        const card = document.createElement("div");
        card.className = "validation-stat";
        card.append(textNode("strong", "", count), textNode("span", "", label));
        stats.append(card);
      });
      summary.append(stats);

      const skillSection = addReportSection(validationContent, "Skill evidence");
      if (!report.skills?.length) {
        skillSection.append(textNode("p", "muted", "No required or preferred skills are defined for this vacancy."));
      } else {
        const wrap = document.createElement("div");
        wrap.className = "table-wrap validation-table-wrap";
        const table = document.createElement("table");
        const head = document.createElement("thead");
        const headerRow = document.createElement("tr");
        ["Skill", "Project", "Experience", "Status", "Evidence"].forEach(
          (label) => headerRow.append(textNode("th", "", label)),
        );
        head.append(headerRow);
        const body = document.createElement("tbody");
        report.skills.forEach((item) => {
          const row = document.createElement("tr");
          const skill = document.createElement("td");
          skill.append(textNode("strong", "validation-skill-name", item.skill));
          skill.append(textNode("small", "validation-skill-type", item.requirement));
          row.append(skill);
          const hasProjectEvidence = Boolean(item.project_evidence?.length);
          const experienceEvidence = [
            ...(item.professional_experience_evidence || []),
            ...(item.internship_experience_evidence || []),
            ...(!item.professional_experience_evidence && !item.internship_experience_evidence
              ? item.experience_evidence || []
              : []),
          ];
          const hasExperienceEvidence = experienceEvidence.length > 0;
          row.append(textNode(
            "td",
            hasProjectEvidence ? "validation-found" : "validation-not-found",
            hasProjectEvidence ? "Found" : "Not found",
          ));
          row.append(textNode(
            "td",
            hasExperienceEvidence ? "validation-found" : "validation-not-found",
            hasExperienceEvidence ? "Found" : "Not found",
          ));
          row.append(textNode(
            "td",
            `validation-status status-${item.status?.toLowerCase().replaceAll(" ", "-") || "unknown"}`,
            item.status,
          ));
          const evidenceCell = document.createElement("td");
          addEvidenceDetails(evidenceCell, [
            ["Project", item.project_evidence],
            ["Professional experience", item.professional_experience_evidence],
            ["Internship experience", item.internship_experience_evidence],
            ...(!item.professional_experience_evidence && !item.internship_experience_evidence
              ? [["Experience", item.experience_evidence]]
              : []),
            ...(!hasProjectEvidence && !hasExperienceEvidence && item.resume_mention
              ? [["Resume mention", item.resume_sentences]]
              : []),
          ]);
          row.append(evidenceCell);
          body.append(row);
        });
        table.append(head, body);
        wrap.append(table);
        skillSection.append(wrap);
      }

      const projectSection = addReportSection(validationContent, "Project analysis");
      projectSection.append(textNode(
        "p",
        "muted validation-section-note",
        "Relevance is textual similarity to the vacancy, not a measure of candidate competence.",
      ));
      if (!report.projects?.length) {
        projectSection.append(textNode("p", "muted", "No academic project descriptions were identified."));
      }
      const projectGrid = document.createElement("div");
      projectGrid.className = "validation-project-grid";
      (report.projects || []).forEach((project) => {
        const card = document.createElement("article");
        card.className = "validation-card validation-project-card";
        const top = document.createElement("div");
        top.className = "validation-card-top";
        top.append(textNode("h4", "", project.title));
        top.append(textNode(
          "span",
          "badge badge-blue",
          project.relevance_percentage === null || project.relevance_percentage === undefined
            ? "Similarity unavailable"
            : `${project.relevance_percentage}% similarity`,
        ));
        card.append(top);
        card.append(textNode(
          "p",
          "validation-card-meta",
          `Technologies: ${(project.technologies || []).join(", ") || "Not identified"}`,
        ));
        if (project.relevant_requirements?.length) {
          card.append(textNode(
            "p",
            "validation-card-meta",
            `Relevant vacancy skills: ${project.relevant_requirements.join(", ")}`,
          ));
        }
        card.append(textNode("p", "validation-card-explanation", project.explanation));
        const details = document.createElement("details");
        details.className = "validation-details";
        details.append(textNode("summary", "", "View Project Details"));
        details.append(textNode("strong", "validation-evidence-label", "Resume description"));
        const description = document.createElement("p");
        description.className = "validation-source-text";
        appendHighlightedDescription(
          description,
          project.description || project.summary,
          project.evidence_sentences,
        );
        details.append(description);
        if (project.evidence_sentences?.length) {
          details.append(textNode(
            "p",
            "muted validation-disclaimer",
            "Highlighted text contains skill evidence used in this report.",
          ));
        }
        card.append(details);
        projectGrid.append(card);
      });
      projectSection.append(projectGrid);

      const experienceSection = addReportSection(validationContent, "Experience analysis");
      const professionalExperiences = report.professional_experience
        || (report.experience || []).filter((item) => item.category !== "internship");
      const internshipExperiences = report.internship_experience
        || (report.experience || []).filter((item) => item.category === "internship");
      [
        ["Professional Experience", professionalExperiences, "No professional experience information found."],
        ["Internship Experience", internshipExperiences, "No internship information found."],
      ].forEach(([title, experiences, emptyText]) => {
        const group = document.createElement("div");
        group.className = "validation-experience-group";
        group.append(textNode("h4", "", title));
        if (!experiences.length) {
          group.append(textNode("p", "validation-empty", emptyText));
        } else {
          experiences.forEach((experience) => {
            const card = document.createElement("article");
            card.className = "validation-card validation-experience-card";
            card.append(textNode("h4", "", experience.job_title));
            const meta = [
              experience.company && experience.company !== "Not available" ? `Company: ${experience.company}` : "",
              experience.date_range && experience.date_range !== "Not available" ? experience.date_range : "",
              experience.duration && experience.duration !== "Not available" ? experience.duration : "",
            ].filter(Boolean);
            if (meta.length) card.append(textNode("p", "validation-card-meta", meta.join(" · ")));
            if (experience.technologies?.length) {
              card.append(textNode("p", "validation-card-meta", `Technologies: ${experience.technologies.join(", ")}`));
            }
            const details = document.createElement("details");
            details.className = "validation-details";
            details.append(textNode("summary", "", "View Experience Details"));
            const list = document.createElement("ul");
            list.className = "validation-evidence";
            (experience.responsibilities || []).forEach((sentence) => list.append(textNode("li", "", sentence)));
            if (list.childElementCount) details.append(list);
            else details.append(textNode("span", "validation-empty", "No responsibility details found."));
            card.append(details);
            group.append(card);
          });
        }
        experienceSection.append(group);
      });

      const qualitySection = addReportSection(validationContent, "Resume quality");
      const quality = report.quality || {};
      const observations = (quality.observations || []).slice(0, 4);
      if (observations.length) {
        const list = document.createElement("ul");
        list.className = "validation-quality-list";
        observations.forEach((observation) => list.append(textNode("li", "", observation)));
        qualitySection.append(list);
      }
      if (quality.disclaimer) {
        qualitySection.append(textNode("p", "muted validation-disclaimer", quality.disclaimer));
      }

      const summarySection = addReportSection(validationContent, "HR summary");
      summarySection.append(textNode("p", "validation-summary", report.hr_summary));
      validationPanel.hidden = false;
    };

    if (initialReport?.textContent) {
      try {
        const report = JSON.parse(initialReport.textContent);
        if (report) renderValidationReport(report);
      } catch (error) {
        showValidationFeedback(error.message || "The saved validation report could not be displayed.", "error");
      }
    }

    validationButton.addEventListener("click", async () => {
      if (validationButton.disabled) return;
      validationButton.disabled = true;
      validationButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Validating…';
      showValidationFeedback("Analysing resume evidence against this vacancy…");
      try {
        const data = await fetchJson(validationButton.dataset.url, {
          method: "POST",
          timeoutMs: 45_000,
          headers: { "X-CSRFToken": validationCsrf },
          body: JSON.stringify({}),
        });
        renderValidationReport(data.report);
        showValidationFeedback("Validation report generated.", "success");
        validationPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (error) {
        showValidationFeedback(error.message || "Candidate validation failed. Please try again.", "error");
      } finally {
        validationButton.disabled = false;
        validationButton.innerHTML = originalButton;
      }
    });
  }

  const vacancySelect = document.getElementById("interviewVacancy");
  const candidateSelect = document.getElementById("interviewCandidate");
  const interviewForm = document.getElementById("interviewForm");
  if (!vacancySelect || !candidateSelect || !interviewForm) return;

  const generateButton = document.getElementById("generateQuestions");
  const saveButton = document.getElementById("saveQuestions");
  const viewSavedButton = document.getElementById("viewSavedQuestions");
  const generatedPanel = document.getElementById("generatedPanel");
  const generatedContainer = document.getElementById("generatedQuestions");
  const savedContainer = document.getElementById("savedQuestions");
  const feedback = document.getElementById("interviewFeedback");
  const categories = JSON.parse(document.getElementById("questionCategories").textContent);
  let generatedQuestions = [];
  let generatedDifficulty = "";
  let isGenerating = false;

  const showFeedback = (message, kind = "info") => {
    feedback.textContent = message;
    feedback.className = `interview-feedback feedback-${kind}`;
    feedback.hidden = !message;
  };

  const resetGenerated = () => {
    generatedQuestions = [];
    generatedDifficulty = "";
    generatedPanel.hidden = true;
    saveButton.disabled = true;
    generatedContainer.replaceChildren();
  };

  const addQuestionGroups = (container, questions, saved = false) => {
    container.replaceChildren();
    categories.forEach((category) => {
      const items = questions.filter((item) => item.category === category);
      if (!items.length) return;

      const section = document.createElement("section");
      section.className = "question-category";
      const heading = document.createElement("div");
      heading.className = "category-heading";
      const title = document.createElement("h3");
      title.textContent = category;
      const count = document.createElement("span");
      count.textContent = String(items.length);
      heading.append(title, count);

      const list = document.createElement("div");
      list.className = "question-list";
      items.forEach((item) => {
        const article = document.createElement("article");
        article.className = "question-item";
        const meta = document.createElement("div");
        meta.className = "question-meta";
        const difficulty = document.createElement("span");
        difficulty.className = "badge badge-blue";
        difficulty.textContent = item.difficulty || generatedDifficulty;
        meta.append(difficulty);
        if (saved && item.generated_at) {
          const date = document.createElement("span");
          date.className = "muted";
          date.textContent = new Date(item.generated_at).toLocaleString();
          meta.append(date);
        }
        const question = document.createElement("p");
        question.textContent = item.question;
        article.append(meta, question);
        if (saved) {
          const details = document.createElement("small");
          details.textContent = `${item.candidate} · ${item.vacancy}`;
          article.append(details);
        }
        list.append(article);
      });
      section.append(heading, list);
      container.append(section);
    });
    if (!container.childElementCount) {
      const empty = document.createElement("div");
      empty.className = "empty-state compact-empty";
      const message = document.createElement("p");
      message.textContent = saved ? "No saved questions match this selection." : "No questions were generated.";
      empty.append(message);
      container.append(empty);
    }
  };

  const loadShortlistedCandidates = async () => {
    candidateSelect.disabled = true;
    generateButton.disabled = true;
    candidateSelect.replaceChildren(new Option("Select a vacancy first", ""));
    resetGenerated();
    showFeedback("");
    if (!vacancySelect.value) return;
    candidateSelect.replaceChildren(new Option("Loading shortlisted candidates…", ""));
    try {
      const endpoint = interviewForm.dataset.candidatesUrl.replace(
        "/0/shortlisted",
        `/${encodeURIComponent(vacancySelect.value)}/shortlisted`,
      );
      const data = await fetchJson(endpoint);
      candidateSelect.replaceChildren(new Option("Select a candidate", ""));
      data.applications.forEach((application) => {
        candidateSelect.add(
          new Option(
            `${application.candidate} · ${application.email || "No email"}`,
            application.candidate_id,
          ),
        );
      });
      if (!data.applications.length) {
        candidateSelect.replaceChildren(new Option("No shortlisted candidates", ""));
      }
      candidateSelect.disabled = data.applications.length === 0;
    } catch (error) {
      candidateSelect.replaceChildren(new Option("Could not load candidates", ""));
      showFeedback(error.message, "error");
    }
  };

  vacancySelect.addEventListener("change", loadShortlistedCandidates);
  candidateSelect.addEventListener("change", () => {
    resetGenerated();
    showFeedback("");
    generateButton.disabled = !candidateSelect.value;
  });

  generateButton.addEventListener("click", async () => {
    if (isGenerating) return;
    if (!vacancySelect.value) {
      showFeedback("Select a vacancy before generating questions.", "error");
      return;
    }
    if (!candidateSelect.value) {
      showFeedback("Select a shortlisted candidate before generating questions.", "error");
      return;
    }
    isGenerating = true;
    generateButton.disabled = true;
    generateButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating…';
    showFeedback("Generating personalised interview questions…", "info");
    try {
      const data = await fetchJson(interviewForm.dataset.generateUrl, {
        method: "POST",
        timeoutMs: 45_000,
        body: JSON.stringify({
          vacancy_id: Number(vacancySelect.value),
          candidate_id: Number(candidateSelect.value),
          difficulty: document.getElementById("interviewDifficulty").value,
          count: Number(document.getElementById("interviewCount").value),
        }),
      });
      if (!data || !Array.isArray(data.questions) || !data.questions.length) {
        throw new Error("Gemini returned no questions. Please try again.");
      }
      generatedQuestions = data.questions;
      generatedDifficulty = data.difficulty;
      addQuestionGroups(generatedContainer, generatedQuestions);
      document.getElementById("generatedSummary").textContent =
        `${generatedQuestions.length} ${generatedDifficulty.toLowerCase()} questions for the selected candidate and vacancy.`;
      generatedPanel.hidden = false;
      saveButton.disabled = false;
      showFeedback("Questions generated. Review them, then save the set if you want to keep it.", "success");
    } catch (error) {
      resetGenerated();
      showFeedback(error.message || "Could not generate questions. Please try again.", "error");
    } finally {
      isGenerating = false;
      generateButton.innerHTML = '<i class="fa-solid fa-sparkles"></i> Generate questions';
      generateButton.disabled = !vacancySelect.value || !candidateSelect.value;
    }
  });

  saveButton.addEventListener("click", async () => {
    if (!generatedQuestions.length || saveButton.disabled) return;
    saveButton.disabled = true;
    try {
      const data = await fetchJson(interviewForm.dataset.saveUrl, {
        method: "POST",
        body: JSON.stringify({
          vacancy_id: Number(vacancySelect.value),
          candidate_id: Number(candidateSelect.value),
          difficulty: generatedDifficulty,
          questions: generatedQuestions,
        }),
      });
      showFeedback(data.message, "success");
      const saved = await loadSavedQuestions();
      if (saved) document.getElementById("savedQuestions").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showFeedback(error.message, "error");
      saveButton.disabled = false;
    }
  });

  const loadSavedQuestions = async () => {
    const url = new URL(interviewForm.dataset.savedUrl, window.location.origin);
    if (vacancySelect.value) url.searchParams.set("vacancy_id", vacancySelect.value);
    if (candidateSelect.value) url.searchParams.set("candidate_id", candidateSelect.value);
    try {
      const data = await fetchJson(url);
      addQuestionGroups(savedContainer, data.questions, true);
      return true;
    } catch (error) {
      showFeedback(error.message, "error");
      return false;
    }
  };

  viewSavedButton.addEventListener("click", loadSavedQuestions);
});
