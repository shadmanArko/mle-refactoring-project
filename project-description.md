# Project Description

You will work with the [King County Jupyter notebook](./King-County.ipynb), which already contains exploratory data analysis, data cleaning, feature engineering, and several Machine Learning models.

The main focus of this project is the refactoring of the data cleaning and feature engineering workflow. The modeling section stays in the notebook so you can see how those transformed features are used later in a full Machine Learning workflow.

## Main Tasks

- Refactor the data cleaning and feature engineering code into Python files.
- Build a reusable pipeline for data cleaning and feature engineering.

### Stretch Tasks

- Refactor the modeling step as well, or extend your pipeline so it also supports the training workflow.
- Build a FastAPI app that supports Create, Read, Update and Delete operations for houses stored in a database, using 5 features.
- Create a `Dockerfile` for the app.
- Run the app inside a Docker container.

If you want a working reference for this optional stretch goal, see [bonus_solution/](./bonus_solution/). It includes a minimal FastAPI + Postgres + Docker example and is meant as a guide, not a required structure.

### Extra (if you still have time)

- Write tests.

## Workflow

```mermaid
flowchart TD
    A[Review the notebook] --> B[Refactor cleaning and feature engineering into Python files]
    B --> C[Build a reusable pipeline]
    C --> D[Optional: Extend the refactor to the modeling step]
    C --> E[Optional: Build the FastAPI CRUD app]
    E --> F[Optional: Add Docker support]
    F --> G[Optional: Run the app in a container]
    C --> H[Extra: Write tests]
```

## Answer the following questions

- What steps did you take to complete the project?
- What challenges did you face?
- What would you do differently if you had more time?
