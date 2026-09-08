import { Public_Sans } from 'next/font/google';
import localFont from 'next/font/local';
import Link from 'next/link';
import { ClerkProvider, UserButton } from '@clerk/nextjs';
import { ThemeProvider } from '@/components/app/theme-provider';
import { ThemeToggle } from '@/components/app/theme-toggle';
import { cn } from '@/lib/shadcn/utils';
import '@/styles/globals.css';

const publicSans = Public_Sans({
  variable: '--font-public-sans',
  subsets: ['latin'],
});

const commitMono = localFont({
  display: 'swap',
  variable: '--font-commit-mono',
  src: [
    {
      path: '../fonts/CommitMono-400-Regular.otf',
      weight: '400',
      style: 'normal',
    },
    {
      path: '../fonts/CommitMono-700-Regular.otf',
      weight: '700',
      style: 'normal',
    },
    {
      path: '../fonts/CommitMono-400-Italic.otf',
      weight: '400',
      style: 'italic',
    },
    {
      path: '../fonts/CommitMono-700-Italic.otf',
      weight: '700',
      style: 'italic',
    },
  ],
});

interface RootLayoutProps {
  children: React.ReactNode;
}

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <ClerkProvider
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      signInFallbackRedirectUrl="/"
      signUpFallbackRedirectUrl="/"
    >
      <html
        lang="en"
        suppressHydrationWarning
        className={cn(
          publicSans.variable,
          commitMono.variable,
          'scroll-smooth font-sans antialiased'
        )}
      >
        <head>
          <title>ShiftSignal Interview</title>
          <meta
            name="description"
            content="A private, AI-guided post-shift hospitality interview"
          />
        </head>
        <body className="overflow-x-hidden">
          <ThemeProvider
            attribute="class"
            defaultTheme="system"
            enableSystem
            disableTransitionOnChange
          >
            <header className="fixed top-0 left-0 z-50 flex w-full items-center justify-between p-4 md:p-6">
              <Link
                href="/"
                className="text-foreground font-mono text-sm font-bold tracking-wider uppercase"
              >
                ShiftSignal
              </Link>
              <div className="flex items-center gap-4">
                <span className="text-muted-foreground hidden font-mono text-xs tracking-wider uppercase md:inline">
                  Staff interview prototype
                </span>
                <UserButton />
              </div>
            </header>

            {children}
            <div className="group fixed bottom-0 left-1/2 z-50 mb-2 -translate-x-1/2">
              <ThemeToggle className="translate-y-20 transition-transform delay-150 duration-300 group-hover:translate-y-0" />
            </div>
          </ThemeProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
