# How the Referee Tracker Works

## Overview

This project collects every foul call made in NBA games, stores it in a database, and lets you explore patterns through an interactive website — for example, which referee calls the most technical fouls, or which players get fouled the most in the playoffs.

---

## Step 1: Getting the Data

The NBA publishes detailed play-by-play data for every game on their public CDN (Content Delivery Network) at `cdn.nba.com`. A CDN is essentially a server that hosts static files anyone can download — think of it like a public file storage system.

For each game, two files are pulled:
- **Play-by-play**: every event in the game (shots, fouls, turnovers, etc.) with timestamps and the players involved
- **Boxscore**: the roster and referee assignments for that game

From these, we extract only the foul events — who committed the foul, what type of foul it was (shooting, technical, flagrant, etc.), and which referee called it.

A Python script handles this automatically. It can run in two modes:
- **Historical**: fetch an entire season's worth of games at once (covering 2019-20 through today)
- **Daily**: run every morning at 11am ET, check if games were played yesterday, and pull only the new data

---

## Step 2: Storing the Data — PostgreSQL

Once extracted, the foul data is written directly into a **PostgreSQL database hosted on Render** (the same cloud platform that runs the API). Nothing is stored locally on the machine running the pipeline — the Python script connects to Render over the internet, writes the foul events straight into the remote database, and disconnects. The data never sits on anyone's laptop.

PostgreSQL is a relational database — think of it as a very structured, queryable spreadsheet system. Data is organized into tables with defined columns and rows, and you can ask it complex questions like *"give me every shooting foul called by referee X on player Y during the 2024-25 playoffs, sorted by count."*

There are four main tables:

| Table | What it stores |
|---|---|
| `games` | One row per game — season, date, teams, and whether it was a playoff game |
| `referees` | One row per referee — their ID and name |
| `players` | One row per player — their ID, name, and team |
| `foul_events` | One row per foul call — links referee, player, game, and foul type together |

The `foul_events` table is the heart of the system. Every row answers: *"In game G, referee R called a [foul type] foul on player P."*

---

## Step 3: The API — Making Data Available Online

The database lives on a server, but the website needs a way to ask it questions. That's what the **API** (Application Programming Interface) does.

Built with **FastAPI** (a Python framework), the API sits between the database and the website. It exposes a set of URLs that the website can call to get data back. For example:

- `/api/referees` → returns all referees ranked by foul count
- `/api/referee/123` → returns details for a specific referee
- `/api/graph` → returns the full network of referee-player connections

Every endpoint supports filters — season, game type (regular vs. playoffs), and foul type — so the website only gets back the data it needs.

The API is hosted on **Render**, a cloud platform that runs the Python server 24/7 so it's always reachable.

---

## Step 4: The Website

The frontend is built with **React** (a JavaScript framework for building interactive UIs) and served as a static website.

It has two views:

**Dashboard** — a searchable list of referees and players. Click any name to see their foul breakdown by type, and a table of who they're most connected to (e.g. which players a referee fouls the most, or which referees called the most fouls on a player).

**Graph** — a 3D network visualization where referees and players are nodes, and the lines between them represent foul relationships. The thicker the line, the more fouls called. You can rotate, zoom, and click any node to see details.

---

## How It All Connects

```
Your laptop
  ├─ fetches raw data from NBA CDN
  ├─ parses foul events in memory
  └─ writes directly to PostgreSQL on Render (over internet)

                    [ Render cloud ]
          ┌─────────────────────────────────┐
          │  PostgreSQL database            │
          │          ↕ (internal network)   │
          │  FastAPI API server             │
          └─────────────────────────────────┘
                          ↓
              React website (your browser)
```

Your laptop is only involved when the pipeline runs — it connects to Render, writes the data, and disconnects. The database and API live entirely in the cloud and are always reachable. The daily automation keeps the database current throughout the season without any manual steps.
