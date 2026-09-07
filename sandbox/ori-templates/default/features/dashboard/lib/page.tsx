import { Layout } from "./layout";

interface Stat {
  label: string;
  value: string | number;
}

interface DashboardPageProps {
  heading: string;
  message: string;
  stats: Stat[];
}

const DashboardHeader = ({
  heading,
  message,
}: Pick<DashboardPageProps, "heading" | "message">): React.ReactNode => (
  <header
    style={{
      marginBottom: "2rem",
    }}
  >
    <h1
      style={{
        margin: "0 0 0.5rem 0",
        fontSize: "1.5rem",
      }}
    >
      {heading}
    </h1>
    <p
      style={{
        margin: 0,
        color: "#666",
      }}
    >
      {message}
    </p>
  </header>
);

const StatsSection = ({
  stats,
}: Pick<DashboardPageProps, "stats">): React.ReactNode => (
  <section
    style={{
      marginBottom: "2rem",
    }}
  >
    <h2
      style={{
        fontSize: "1rem",
        marginBottom: "1rem",
      }}
    >
      Stats
    </h2>
    <ul
      style={{
        listStyle: "none",
        padding: 0,
        margin: 0,
      }}
    >
      {stats.map((stat, i) => (
        <li
          key={i}
          style={{
            marginBottom: "0.5rem",
          }}
        >
          {stat.label}: <strong>{stat.value}</strong>
        </li>
      ))}
    </ul>
  </section>
);

export const DashboardPage = ({
  heading,
  message,
  stats,
}: DashboardPageProps): React.ReactNode => (
  <Layout title="Dashboard">
    <DashboardHeader
      heading={heading}
      message={message}
    />
    <StatsSection stats={stats} />
    <footer>
      <span
        style={{
          background: "#000",
          color: "#fff",
          padding: "0.25rem 0.5rem",
          fontSize: "0.875rem",
        }}
      >
        Powered by Ori
      </span>
    </footer>
  </Layout>
);
