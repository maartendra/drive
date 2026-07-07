import { useAuth } from "@/features/auth/Auth";
import { useConfig } from "@/features/config/ConfigProvider";
import { ExplorerTree } from "@/features/explorer/components/tree/ExplorerTree";
import {
  HelpMenu,
  IconSize,
  MainLayout,
  StorageGaugeButton,
  StorageGaugeInformation,
} from "@gouvfr-lasuite/ui-kit";
import { HeaderIcon, HeaderRight } from "../header/Header";
import {
  GlobalExplorerProvider,
  NavigationEvent,
  useGlobalExplorer,
} from "@/features/explorer/components/GlobalExplorerContext";
import { ExplorerRightPanelContent } from "@/features/explorer/components/right-panel/ExplorerRightPanelContent";
import { GlobalLayout } from "../global/GlobalLayout";
import { LeftPanelMobile } from "../left-panel/LeftPanelMobile";
import { useRouter } from "next/router";
import { useSyncUserLanguage } from "../../hooks/useSyncUserLanguage";
import { Item } from "@/features/drivers/types";
import { ReleaseNoteAuto } from "@/features/ui/components/release-note";
import {
  formatSizeTo,
  setManualNavigationItemId,
} from "@/features/explorer/utils/utils";
import { ColumnPreferencesProvider } from "@/features/explorer/hooks/useColumnPreferences";
import { EntitlementDisclaimers } from "@/features/entitlement-disclaimers/EntitlementDisclaimers";
import { useEntitlements } from "@/features/entitlement-disclaimers/hooks/useEntitlements";
import { GearRounded } from "@gouvfr-lasuite/ui-kit/icons";
import {
  Button,
  Modal,
  ModalProps,
  ModalSize,
  ModalTab,
  useModal,
} from "@gouvfr-lasuite/cunningham-react";
import { useTranslation } from "react-i18next";
import i18n from "@/features/i18n/initI18n";
import { useMemo } from "react";

export const getGlobalExplorerLayout = (page: React.ReactElement) => {
  return <GlobalExplorerLayout>{page}</GlobalExplorerLayout>;
};

export const GlobalExplorerLayout = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  return (
    <GlobalLayout>
      <ColumnPreferencesProvider>
        <ReleaseNoteAuto />
        <EntitlementDisclaimers />
        <ExplorerLayout>{children}</ExplorerLayout>
      </ColumnPreferencesProvider>
    </GlobalLayout>
  );
};

/**
 * This layout is used for the explorer page.
 * It is used to display the explorer tree and the header.
 */
export const ExplorerLayout = ({
  children,
}: {
  children: React.ReactNode;
  isMinimalLayout?: boolean;
}) => {
  const router = useRouter();

  const isMinimalLayout = router.query.minimal === "true";
  const itemId = router.query.id as string;
  const onNavigate = (e: NavigationEvent) => {
    // Only keep "minimal" in the query string so that when navigating, to keep the minimal layout on the next page
    // the minimal layout state is preserved; all other query params are dropped intentionally.
    const { minimal } = router.query;
    const item = e.item as Item;
    const query = minimal ? { minimal } : {};
    // If the itemId is a favorite item, we need to get the favorite items. cf onLoadChildren in GlobalExplorerProvider.tsx
    const id = item.originalId ?? item.id;
    setManualNavigationItemId(id);
    router.push({ pathname: `/explorer/items/${id}`, query });
  };

  useSyncUserLanguage();

  return (
    <GlobalExplorerProvider
      itemId={itemId}
      displayMode="app"
      onNavigate={onNavigate}
    >
      <ExplorerPanelsLayout isMinimalLayout={isMinimalLayout}>
        {children}
      </ExplorerPanelsLayout>
    </GlobalExplorerProvider>
  );
};

export const ExplorerPanelsLayout = ({
  children,
  isMinimalLayout,
}: {
  children: React.ReactNode;
  isMinimalLayout?: boolean;
}) => {
  const {
    rightPanelOpen,
    setRightPanelOpen,
    item,
    rightPanelForcedItem: rightPanelItem,
    isLeftPanelOpen,
    setIsLeftPanelOpen,
  } = useGlobalExplorer();

  const { user } = useAuth();

  return (
    <MainLayout
      enableResize
      rightPanelContent={<ExplorerRightPanelContent item={rightPanelItem} />}
      rightPanelIsOpen={rightPanelOpen}
      onToggleRightPanel={() => setRightPanelOpen(!rightPanelOpen)}
      leftPanelContent={user ? <ExplorerTree /> : <LeftPanelMobile />}
      leftPanelFooter={<LeftPanelFooter />}
      isLeftPanelOpen={isLeftPanelOpen}
      hideLeftPanelOnDesktop={!user || isMinimalLayout}
      setIsLeftPanelOpen={() => setIsLeftPanelOpen(!isLeftPanelOpen)}
      icon={<HeaderIcon />}
      rightHeaderContent={
        <HeaderRight displaySearch={isMinimalLayout} currentItem={item} />
      }
    >
      {children}
    </MainLayout>
  );
};

const LeftPanelFooter = () => {
  const { config } = useConfig();
  const { data: entitlements } = useEntitlements();
  const quota = entitlements?.quota;
  console.log("quota", quota);
  const helpMenuConfig = config?.FRONTEND_HELP_MENU_CONFIG;
  const hasHelpMenu =
    !!helpMenuConfig && Object.keys(helpMenuConfig).length > 0;

  const settingsModal = useModal();

  return (
    <div className="c__left-panel__footer__drive">
      {hasHelpMenu && (
        <HelpMenu
          documentationUrl={helpMenuConfig.documentationUrl}
          legal={helpMenuConfig.legal}
          onContactUs={
            helpMenuConfig.supportEmail
              ? () => window.open(helpMenuConfig.supportEmail)
              : undefined
          }
        />
      )}
      {/* <Button
        icon={<GearRounded />}
        color="neutral"
        variant="tertiary"
        size={"small"}
      /> */}
      <LeftPanelFooterStorageGauge onClick={settingsModal.open} />
      <SettingsModal {...settingsModal} />
    </div>
  );
};

const SettingsModal = (props: Pick<ModalProps, "isOpen" | "onClose">) => {
  const { t } = useTranslation();
  const tabs: ModalTab[] = [
    {
      id: "tab1",
      label: i18n.t("settings_modal.tabs.storage.title"),
      title: i18n.t("settings_modal.tabs.storage.title"),
      content: <SettingsModalStorageTab />,
    },
  ];

  return (
    <Modal
      variant="tab"
      size={ModalSize.LARGE}
      sidebarTitle={t("settings_modal.title")}
      tabs={tabs}
      constraints={{ preferredHeight: "500px" }}
      {...props}
    />
  );
};

const SettingsModalStorageTab = () => {
  const quota = useQuota();
  if (!quota) {
    return null;
  }
  return (
    <div>
      <StorageGaugeInformation
        used={quota.usageFormatted}
        total={quota.limitFormatted}
        unit="GB"
      />
    </div>
  );
};

const LeftPanelFooterStorageGauge = (props: { onClick: () => void }) => {
  const quota = useQuota();

  if (quota?.state === "default") {
    return (
      <StorageGaugeButton
        used={quota.usageFormatted}
        total={quota.limitFormatted}
        onClick={props.onClick}
      />
    );
  }
  return ":)";
};

const useQuota = () => {
  const { data: entitlements } = useEntitlements();

  const quota = useMemo(() => {
    const quota = entitlements?.quota;
    if (!quota) {
      return null;
    }
    if (quota.state === "default") {
      const usageFormatted = formatSizeTo(quota.usage!, "GB");
      const limitFormatted = formatSizeTo(quota.limit!, "GB");
      return {
        ...quota,
        usageFormatted: usageFormatted,
        limitFormatted: limitFormatted,
      };
    }
    return null;
  }, [entitlements]);
  return quota;
};
